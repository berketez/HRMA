/* ====================================================================
   HRMA Analiz Güvertesi — Cıvatalı Bağlantı Paneli (Dalga 3)
   --------------------------------------------------------------------
   POST /api/bolted-joint sonucunu çizer (STRUCTURAL sekmesinde
   structural_panel'in altında ikinci panel):
   - Cıvata formu: boyut (M4–M24), sınıf (ISO 898-1 / ISO 3506-1), sayı,
     sıkma boyu, üye malzemesi, yağlama, yeniden kullanım
   - Tork önerisi + tork-kontrollü sıkmada ±%25 ön-yük saçılım bandı
   - Ayrılma (separation) marjı rozeti + emniyet faktörü kartları
     (Shigley 10th ed. Eq. 8-24…8-30)
   Backend: hrma/analysis/bolted_joint.py.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    var U = window.AnalysisDock.ui;
    var T = U.t;                         // çeviri kısayolu

    // Sunucudan gelen SERBEST METİN (gerekçe/beyan cümlesi): sözlükte
    // karşılığı varsa Türkçe basılır, yoksa metin AYNEN döner (asla
    // anahtar, asla boş). structural_panel / cfd_panel ile aynı yardımcı.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    // bolted_joint.py THREAD_STRESS_AREA_MM2 anahtarlarıyla birebir
    var SIZES = ['M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M14', 'M16',
                 'M18', 'M20', 'M22', 'M24'].map(function (s) { return [s, s]; });

    var CLASSES = [
        ['8.8', '8.8 (ISO 898-1)'],
        ['10.9', '10.9 (ISO 898-1)'],
        ['12.9', '12.9 (ISO 898-1)'],
        ['A2-70', 'A2-70 stainless (ISO 3506-1)', 'joint.classA270'],
    ];

    // FALLBACK listesi — /api/materials kataloğu yüklenemezse kullanılır
    // (sıkılan üye malzemesi; katalog gelirse 'bolt'+'structural' etiketli
    // tam liste bunun yerine geçer)
    // ÖH D24 / OH-D23-03 — varsayılan malzeme: ÖNCE sunucunun ilan
    // ettiği değer (materials_catalog.js -> /api/materials.
    // default_structural_material). Katalog betiği hiç yüklenmemişse
    // son çare ikiz sabit kullanılır; bu ikizin sunucudan AYRIŞMASI
    // bekçiyle yasaktır (tests/test_d24_fix_asamasi.py, panel
    // ikizlerini sunucu değeriyle EŞİTLER). Boş bırakmak seçenek
    // değildir: cıvatalı bağlantı ucu member_material'ı ZORUNLU
    // tutar (ÖH D15 / P5B1-05 fail-closed) ve panel varsayılan
    // koşumda 400 alırdı.
    var VARSAYILAN_MALZEME = (typeof window.HRMAMaterials !== 'undefined'
        && window.HRMAMaterials.defaultStructuralMaterial)
        ? window.HRMAMaterials.defaultStructuralMaterial()
        : 'aluminum_6061';   /* ikiz — bekçi sunucuyla eşitler */

    var MEMBER_MATERIALS = [
        ['aluminum_6061', 'Aluminum 6061-T6'],
        ['steel', 'Steel (generic)'],
        ['steel_4130', 'Steel AISI 4130'],
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V'],
        ['inconel_718', 'Inconel 718'],
    ];

    var LUBRICATION = [
        ['false', 'Dry assembly (K = 0.20)', 'joint.dry'],
        ['true', 'Lubricated (K = 0.15)', 'joint.lubricated'],
    ];

    var REUSE = [
        ['true', 'Reusable — preload 75% of proof', 'joint.reusable'],
        ['false', 'Permanent — preload 90% of proof', 'joint.permanent'],
    ];

    function sfKind(sf, warnBelow) {
        if (sf == null || !Number.isFinite(sf)) return 'dim';
        if (sf < 1.0) return 'err';
        if (sf < (warnBelow == null ? 1.5 : warnBelow)) return 'warn';
        return 'ok';
    }

    // ==================================================================
    // P11B4-09 — KART HÜKMÜ NOMİNAL DEĞİL YÖNETİCİ DEĞERDEN OKUNUR
    // ==================================================================
    // Ölçülen (docs/scofield/raw/OH/D15/ui-paneller/a2/b4_ONCE.json),
    // panelin KENDİ varsayılanlarıyla (40 bar, 8×M8 8.8, 20 mm sıkma,
    // Al 6061):
    //   proof_SF            1,2157  (kartta, YEŞİL)  ⟷ proof_SF_min            0,9900
    //   overload_factor_nL  3,4444  (kartta, YEŞİL)  ⟷ overload_factor_nL_min  0,8611
    //   separation_factor_n0 6,6720 (kartta, YEŞİL)  ⟷ separation_factor_n0_min 5,0040
    // Modülün kendi beyanı (`safety_factors.governing_basis`) hangisinin
    // bağlayıcı olduğunu ADIYLA söylüyor: "proof/yield evaluated at
    // maximum preload (+25%), separation at minimum preload (−25%) per
    // NASA-STD-5020A Sec. 6.2 / Shigley Sec. 8-8". Yani ekrandaki üç
    // yeşil kartın ikisinin ARKASINDAKİ bağlayıcı değer 1,0'ın ALTINDA
    // ve o sayılar ekranda hiç yoktu (nL 0,861 hiçbir yerde SAYI olarak
    // görünmüyordu).
    //
    // Kart artık: manşette NOMİNAL sayı, altında YÖNETİCİ sayı; RENK
    // yöneticiden gelir. Sayı hesaplanmaz — ucun `*_min` alanı okunur;
    // alan yoksa eski davranış (nominalden renk) korunur ve kartta
    // yönetici satırı HİÇ çıkmaz (fail-closed, uydurma yok).
    function yoneticiSf(sf, nominalAd, yoneticiAd) {
        var nom = sf[nominalAd];
        var yon = sf[yoneticiAd];
        return {
            nominal: nom,
            yonetici: (typeof yon === 'number' && isFinite(yon)) ? yon : null,
            // Hüküm bağlayıcı değerden okunur; yoksa nominalden.
            hukum: (typeof yon === 'number' && isFinite(yon)) ? yon : nom,
            ad: yoneticiAd,
        };
    }

    // Kartın alt satırı: yönetici alanın ADI ve SAYISI. Yeni çeviri
    // anahtarı açılmaz — makine alan adı veri olarak basılır.
    function yoneticiNot(g) {
        if (g.yonetici == null) return '';
        return g.ad + ' ' + U.fmt(g.yonetici, 3);
    }

    /* P11B4-10 — bayrağın ÜÇ hâli ayrı ayrı okunur: ayrıldı / ayrılmadı /
       uç söylemedi. Boolean olmayan değer "hayır"a çevrilmez (fail-closed). */
    function ayrilmaImi(v) {
        if (v === true) return 'YES';
        if (v === false) return 'no';
        return '—';
    }

    function fmtKN(n) {
        // ÖH D31 · OH-D30-06: biçim tek kaynaktan (I18N.number) — TR kipinde virgül.
        return (n == null || !Number.isFinite(n)) ? '—' : U.num(n / 1e3, 2);
    }

    // ==================================================================
    // Z5-C3 / P17B2-12 — ROZET ŞERİDİ GÖRÜNÜR HÂLE GETİRİLDİ
    // ------------------------------------------------------------------
    // ÖLÇÜLEN KUSUR (görsel tur): "üç rozetin ikisi ekranda YOK; görünen
    // tek rozet sönük gri ve 1.164 px aşağıda". Ölçüldü (node koşumu,
    // docs/scofield/raw/OH/Z5/c/olcum_c3_render_once.txt): üç rozet de
    // ÜRETİLİYOR, sorun ÜRETİMDE değil YERLEŞİMDE ve ANLAMDA:
    //   * şerit 10 alanlık formun ALTINDA, sayfanın ~1.164 px aşağısında
    //     akıp gidiyor — kullanıcı hükmü görmek için kaydırmak zorunda;
    //   * son iki rozet DURUM taşımıyordu (ikisi de düz 'info' cyan), yani
    //     hüküm rengiyle künye rengi ayırt edilemiyordu;
    //   * veri gelmese bile üçü de basılıyordu ("— × — class —"), yani
    //     ölçülmemiş bir künye ölçülmüş gibi duruyordu.
    //
    // ARTIK: şerit panel gövdesinin ÜSTÜNE yapışır (position:sticky), üç
    // rozet de GERÇEK durum renklerini taşır ve alanı olmayan rozet HİÇ
    // BASILMAZ (fail-closed) — uydurma "—" künyesi yok.
    // ==================================================================
    var BADGE_STRIP_STYLE = 'display:flex; flex-wrap:wrap; gap:8px;'
        + ' margin:0 0 8px; padding:8px 0; position:sticky; top:0; z-index:3;'
        + ' background:var(--hd-panel, rgba(6,14,26,0.96));'
        + ' border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));';

    // Cıvata künyesi rozeti: ÜÇ alanın üçü de gelmişse basılır.
    function boltIdentityBadge(bolt) {
        if (bolt.count == null || !bolt.size || !bolt.property_class) return '';
        return U.badge(String(bolt.count) + ' × ' + String(bolt.size) + ' '
            + T('panel.joint.classWord', 'class') + ' '
            + String(bolt.property_class),
            // Künye bir HÜKÜM değil, bir kimliktir: nötr ton (Z5-C2 ile
            // aynı ilke — yeşil yalnız "geçti" demektir).
            'info', bolt.strength_source || '');
    }

    // Cıvata gerilme hükmü rozeti: proof SF varsa GERÇEK durum rengiyle.
    // (Eskiden bu hüküm yalnız kartta duruyordu; şeritte hiç yoktu.)
    function proofBadge(sf) {
        if (!Number.isFinite(sf.proof_SF)) return '';
        // P11B4-09: rozetin RENGİ de bağlayıcı değerden okunur; sayı
        // nominal kalır (ucun manşet alanı odur), renk hükmü taşır.
        var gp = yoneticiSf(sf, 'proof_SF', 'proof_SF_min');
        // ÇEVİRİ ANAHTARI NOTU (Z5-C, ana modele devir): bu etiketin
        // anahtarı `panel.joint.badgeProof`, Z5 i18n paketi tarafından
        // i18n_common.js'e İKİ DİLDE eklendi (EN 'BOLT STRESS' / TR 'CIVATA
        // GERİLMESİ'). Bu paket i18n dosyalarına DOKUNMADI. Anahtarın tek
        // tüketicisi burasıdır: bu satır makine dizesine çevrilirse anahtar
        // ÖLÜR ve tests/test_i18n_common.py::test_every_dictionary_key_is_used
        // kırmızıya döner — iki değişiklik BİRLİKTE yapılmalıdır.
        return U.badge(T('panel.joint.badgeProof', 'BOLT STRESS') + ': '
            + U.fmt(sf.proof_SF, 2), sfKind(gp.hukum, 1.2),
            'safety_factors.proof_SF — S_p·A_t / F_bolt (Shigley Eq. 8-28)'
            + (gp.yonetici != null ? ' — ' + yoneticiNot(gp) : ''));
    }

    function render(data, root) {
        var j = (data && data.joint) || {};
        var bolt = j.bolt || {};
        var pre = j.preload || {};
        var tq = j.torque || {};
        var st = j.stiffness || {};
        var loads = j.loads || {};
        var sf = j.safety_factors || {};
        var sep = j.separation || {};

        // P11B4-09: hüküm bağlayıcı (kötü-durum) değerden okunur.
        var gProof = yoneticiSf(sf, 'proof_SF', 'proof_SF_min');
        var gNl = yoneticiSf(sf, 'overload_factor_nL', 'overload_factor_nL_min');
        var gN0 = yoneticiSf(sf, 'separation_factor_n0', 'separation_factor_n0_min');
        // Modülün kendi "hangisi yönetici" cümlesi; yoksa boş dize.
        var govBasis = (typeof sf.governing_basis === 'string')
            ? SRV(sf.governing_basis) : '';

        // ---- Rozetler (fail-closed: alanı olmayan rozet basılmaz) ----
        var badges = '';
        if (sep.separated === true) {
            badges += U.badge(T('panel.joint.separated', 'JOINT SEPARATED'), 'err',
                T('panel.joint.separatedTip',
                  'External load exceeds the preload capacity — the joint opens'));
        } else if (sep.separated === false) {
            badges += U.badge(T('panel.joint.closed', 'JOINT CLOSED'),
                sfKind(gN0.hukum),
                U.tf('panel.joint.n0Tip', { n0: U.fmt(sf.separation_factor_n0, 2) },
                     'Separation factor n0 = {n0}'));
        }
        badges += proofBadge(sf);
        badges += boltIdentityBadge(bolt);
        if (j.source) {
            badges += U.badge(T('panel.joint.model', 'MODEL: SHIGLEY CH. 8'),
                              'info', j.source);
        }

        var scatter = Array.isArray(tq.preload_scatter_band_N)
            ? tq.preload_scatter_band_N : [null, null];

        var head = document.createElement('div');
        head.innerHTML = (badges
            ? '<div style="' + BADGE_STRIP_STYLE + '">' + badges + '</div>'
            : '')
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.joint.cardTorque', 'Recommended torque'),
                U.fmt(tq.recommended_torque_Nm, 1), 'N·m',
                'info', 'T = K·F_i·d, K = ' + U.fmt(tq.K_nut_factor, 2)
                + ' (' + (tq.condition || '—') + ')')
            + U.statCard(T('panel.joint.cardPreload', 'Preload F_i'), fmtKN(pre.preload_N), 'kN', null,
                pre.basis || '')
            + U.statCard(U.tf('panel.joint.cardScatter', { pct: U.fmt(tq.preload_uncertainty_pct, 0) },
                              'Preload scatter ±{pct}%'),
                fmtKN(scatter[0]) + ' – ' + fmtKN(scatter[1]), 'kN', 'warn',
                T('panel.joint.cardScatterTip',
                  'Torque-controlled tightening scatter band (Shigley Sec. 8-8)'))
            + U.statCard(T('panel.joint.cardProofSf', 'Proof SF'),
                U.fmt(gProof.nominal, 2), yoneticiNot(gProof),
                sfKind(gProof.hukum, 1.2),
                'S_p·A_t / F_bolt (Shigley Eq. 8-28) — ' + govBasis)
            + U.statCard(T('panel.joint.cardOverload', 'Overload factor n_L'),
                U.fmt(gNl.nominal, 2), yoneticiNot(gNl),
                sfKind(gNl.hukum, 1.2), 'Shigley Eq. 8-29 — ' + govBasis)
            + U.statCard(T('panel.joint.cardSeparation', 'Separation factor n0'),
                U.fmt(gN0.nominal, 2), yoneticiNot(gN0),
                sfKind(gN0.hukum), 'F_i / (P·(1−C)) — Shigley Eq. 8-30 — ' + govBasis)
            + '</div>';
        root.appendChild(head);

        // ---- Tablolar ----
        var tail = document.createElement('div');
        var html = U.sectionTitle(T('panel.joint.secLoads', 'Load Sharing'));
        html += U.kvTable([
            [T('panel.joint.pressureBasis', 'Pressure load basis'), (loads.pressure_bar == null ? '—'
                : U.tf('panel.joint.pressureBasisValue', { p: U.fmt(loads.pressure_bar, 1) },
                       '{p} bar on seal area'))],
            [T('panel.joint.totalExternal', 'Total external load'),
             fmtKN(loads.total_external_load_N) + ' kN'],
            [T('panel.joint.externalPerBolt', 'External load per bolt'),
             fmtKN(loads.external_load_per_bolt_N) + ' kN'],
            [T('panel.joint.boltTotal', 'Bolt total load F_b'), fmtKN(loads.bolt_total_load_N) + ' kN',
             'F_b = F_i + C·P (Shigley Eq. 8-24)'],
            [T('panel.joint.memberClamp', 'Member clamp load F_m'),
             fmtKN(loads.member_clamp_load_N) + ' kN',
             T('panel.joint.memberClampTip',
               'F_m = F_i − (1−C)·P (Shigley Eq. 8-25) — ≤ 0 means separation')],
            [T('panel.joint.jointConstant', 'Joint constant C'), U.fmt(st.joint_constant_C, 3),
             st.model || ''],
            /* ÖH D26 · P11B4-10 — AYRILMA BLOĞUNUN ÇİFTİ TEKİLLEŞİYORDU.

               ÖLÇÜLDÜ (a3/once.json, taban 7751531): uç `separation`
               bloğunda ALTI alan yayımlıyor, panel İKİSİNİ okuyordu —
                 separated                          okunuyor
                 separation_load_per_bolt_N         okunuyor
                 separated_nominal_preload          0
                 margin                             0
                 margin_nominal                     0
                 separation_load_per_bolt_nominal_N 0
               Modülün kendi beyanı (`safety_factors.governing_basis`)
               ayrılmanın MİNİMUM ön-yükte (−%25) değerlendirildiğini
               söylüyor; nominal ön-yükteki karşılığı ise ayrı alanda
               duruyor. İkisi AYNI ŞEY DEĞİLDİR ve ekranda tek sayı gibi
               görünüyordu: kötü-durumda ayrılan bir bağlantı, nominalde
               ayrılmıyor olabilir (`separated` ⟷ `separated_nominal_preload`)
               ve kullanıcı hangi ön-yükte ne olduğunu okuyamıyordu.

               Sayı türetilmez: ucun alanları YAN YANA basılır, makine
               adlarıyla; alan yoksa em tire. */
            [T('panel.joint.separationLoad', 'Separation load per bolt'),
             fmtKN(sep.separation_load_per_bolt_N) + ' kN'
                + ' <span style="color:var(--hd-ink-dim, #7d97a5);">/ '
                + fmtKN(sep.separation_load_per_bolt_nominal_N)
                + ' kN</span>',
             'separation_load_per_bolt_N (min preload, governing) / '
                + 'separation_load_per_bolt_nominal_N'],
            [T('panel.joint.separationMargin', 'Separation margin n_0'),
             U.fmt(sep.margin, 3)
                + ' <span style="color:var(--hd-ink-dim, #7d97a5);">/ '
                + U.fmt(sep.margin_nominal, 3) + '</span>',
             'margin (min preload, governing) / margin_nominal'],
            [T('panel.joint.separatedPair', 'Separated? (min / nominal preload)'),
             ayrilmaImi(sep.separated) + ' / ' + ayrilmaImi(sep.separated_nominal_preload),
             'separated / separated_nominal_preload'],
        ]);

        html += U.sectionTitle(T('panel.joint.secBolt', 'Bolt Data'));
        html += U.kvTable([
            [T('panel.joint.stressArea', 'Stress area A_t'), U.fmt(bolt.stress_area_mm2, 1) + ' mm²',
             T('panel.joint.stressAreaTip', 'ISO 898-1:2013 Table A.1 (coarse thread)')],
            [T('panel.joint.proofYieldUts', 'Proof / yield / ultimate'),
             U.fmt(bolt.proof_strength_MPa, 0) + ' / '
                + U.fmt(bolt.yield_strength_MPa, 0) + ' / '
                + U.fmt(bolt.ultimate_strength_MPa, 0) + ' MPa',
             bolt.strength_source || ''],
            [T('panel.joint.proofLoad', 'Proof load F_p'), fmtKN(pre.proof_load_N) + ' kN'],
            [T('panel.joint.memberMaterial', 'Member material'), st.member_material || '—'],
        ]);

        html += U.listBlock(T('common.warnings', 'Warnings'), j.warnings, 'warn');
        html += U.listBlock(T('common.assumptions', 'Assumptions'), j.assumptions, 'dim');
        tail.innerHTML = html;
        root.appendChild(tail);
        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, j, { deep: true });
    }

    window.AnalysisDock.register({
        id: 'joint',
        title: 'Bolted Joint — Preload, Torque & Separation (Shigley)',
        titleKey: 'panel.joint.title',
        category: 'STRUCTURAL',
        endpoint: '/api/bolted-joint',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['pressure_bar', 'Chamber Pressure (bar)', 40, 1, 'common.f.chamberPressureBar', 'panel.joint.help.pressure_bar'],
            ['seal_diameter_mm', 'Seal / Effective Diameter (mm)', 100, 1, 'panel.joint.fSealDiameter', 'panel.joint.help.seal_diameter_mm'],
            ['bolt_count', 'Bolt Count', 8, 1, 'panel.joint.fBoltCount', 'panel.joint.help.bolt_count'],
            ['size', 'Bolt Size', 'M8', SIZES, 'panel.joint.fBoltSize', 'panel.joint.help.size'],
            ['property_class', 'Property Class', '8.8', CLASSES, 'panel.joint.fPropertyClass', 'panel.joint.help.property_class'],
            ['grip_length_mm', 'Grip Length (mm)', 20, 1, 'panel.joint.fGripLength', 'panel.joint.help.grip_length_mm'],
            ['member_material', 'Member Material', VARSAYILAN_MALZEME, MEMBER_MATERIALS,
             'panel.joint.fMemberMaterial', 'panel.joint.help.member_material'],
            ['lubricated', 'Thread Condition', 'false', LUBRICATION, 'panel.joint.fThreadCondition', 'panel.joint.help.lubricated'],
            ['reusable', 'Connection Type', 'true', REUSE, 'panel.joint.fConnectionType', 'panel.joint.help.reusable'],
            ['external_axial_load_n', 'Extra Axial Load (N, optional)', '', 100,
             'panel.joint.fExtraAxial', 'panel.joint.help.external_axial_load_n'],
        ],
        fromResults: function (r) {
            var m = (r && r.motor) || r || {};
            var out = {};
            if (Number.isFinite(m.chamber_pressure)) {
                out.pressure_bar = m.chamber_pressure;
            }
            // Sızdırmazlık çapı önerisi: hazne iç çapı (O-ring yüz contası)
            // BİRİM (2026-07-30 ölçümü): koşulsuz `* 1000` yalnız hibritte
            // doğruydu; katı (75,0) ve sıvı (120,0) motorlarda değer zaten
            // MİLİMETRE geliyor ve panel 75 m / 120 m'lik conta çapıyla
            // cıvata hesabı yapıyordu.
            var sealMm = U.readLengthMM(r, 'chamber_diameter');
            if (Number.isFinite(sealMm)) {
                out.seal_diameter_mm = sealMm;
            }
            // V301/K-C1 (KT-22): katı sayfada malzeme ana tasarımın KASA
            // malzemesidir (structural_analysis.case_analysis.case_material).
            // ÖLÇÜLDÜ (denetim A-kati ekran_en.json): panel kasa 'steel' iken
            // kendi varsayılanıyla (VARSAYILAN_MALZEME, Al 6061) hesaplıyordu. Yanıtta
            // malzeme yoksa varsayılan kalır ve bu ADIYLA beyan edilir
            // (güvertenin __withheld künyesi); seçenek listesinde olmayan ad
            // güvertenin kendi kapısında durur (istek gönderilmez).
            if (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function'
                    && window.AnalysisDock.getMotorType() === 'solid') {
                var kasaMalz = U.readChamberMaterial ? U.readChamberMaterial(r) : undefined;
                if (typeof kasaMalz === 'string' && kasaMalz) {
                    out.member_material = kasaMalz;
                } else {
                    out.member_material = VARSAYILAN_MALZEME;
                    var gk = {};
                    gk.member_material = 'case_material_not_in_results: the solid motor result '
                        + 'publishes no case material, so the panel default '
                        + VARSAYILAN_MALZEME + ' is used';
                    out[U.WITHHELD_KEY || '__withheld'] = gk;
                }
            }
            return out;
        },
        render: render,
    });

    // Merkezi katalog yüklüyse üye malzemesi select'ini 'bolt'+'structural'
    // etiketli listeyle doldur; değilse fallback aynen kalır.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'joint', fieldId: 'member_material',
            tags: ['bolt', 'structural'], fallback: MEMBER_MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render (dry-run)
    window.JointPanel = { _render: render };
})();
