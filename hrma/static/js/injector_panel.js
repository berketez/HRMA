/* ====================================================================
   HRMA Injector Design Panel (liquid + advanced — TEK kaynak)
   --------------------------------------------------------------------
   /api/injector-design endpoint'ini UI'a bağlar (sözleşme:
   docs/10_Enjektor_ARGE.md bölüm B.2/C). sixdof_panel.js deseni.

   Kullanıcıya görünen tüm metinler İNGİLİZCE (v2.5.2 dil birliği).
   Şema çizimleri injector_schematics.js'ten gelir (varsa).

   Kullanım:
     <script src="/static/js/injector_schematics.js"></script>
     <script src="/static/js/injector_panel.js"></script>
     InjectorPanel.init({
         anchorId: 'trajectoryPanel',   // panelin ÖNÜNE ekleneceği element (ops.)
         motorType: 'hybrid'|'liquid',  // tip seçici filtreler + varsayılanlar
         resultsProvider: function () {
             // Mevcut hesap sonucundan otomatik doldurma; null → form değerleri
             // Dönen alanlar: mdot_ox, mdot_fuel, Pc_bar, T_c_K, mw_gas,
             //                rho_ox, rho_fuel (hepsi opsiyonel)
         }
     });

   V301/E2 (hibrit): panel artık ana tasarımın devre çözümüyle EŞLENİR.
     InjectorPanel.engineValuesFromResults(results, request) — /calculate
       yanıtından (+ isteğin kendisinden) panelin alan değerlerini kurar
       (saf işlev, düğümde sınanır);
     InjectorPanel.syncFromEngine(values) — alanları doldurur, rol notunu
       basar ve tasarımı bir kez koşturur (aynı girdiler → devrenin
       sayıları);
     InjectorPanel.followMainType(tip) — hesaptan ÖNCE ana formun tip
       seçimini izler (çelişen şema gösterilmez). V301/H2: tek akışkanlı
       koaksiyel eleman artık devrede; panel onu da eşler ve tasarlar.
   V301/L-C (sıvı, SV-13): sıvı sayfasının ayrı eşlemesi (liquid.html,
     yalnız ṁ/Pc/ρ beş alanı) söküldü; sıvı panel de AYNI iki saf işlevden
     geçer: engineValuesFromResults(sonuç) motorun yanıtta yayımladığı
     devre girdisini (injection_system.circuit_request: tip, ṁ, Pc, ρ,
     ΔP/Pc, akışkanlar, eleman sayısı/çift sayısı, pintle ölçüleri,
     kullanıcı Cd'si) okur, specFromValues yükü kurar; uç (/api/injector-
     design) motorun TEK sıvı devre çağrısından geçer. Hesaptan önce panel
     ana formun tipini motorun eşlemesiyle (INJECTOR_TYPE_CIRCUIT_MODEL,
     init({circuitModel})) izler.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    let cfg = {};
    let lastDesign = null;          // dil değişiminde yeniden çizmek için
    // lastDesign HANGİ tip için hesaplandı? Kullanıcı tipi değiştirip
    // yeniden koşmadıysa eski geometriyi yeni tipin çizimine BASMAK
    // yanlış bilgi olurdu (pintle sayılarıyla swirl çizmek gibi).
    let lastDesignType = null;

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    // Uçtan gelen METNİ işaretleme olarak DEĞİL metin olarak basmak için
    // (ÖH D30 / P11B5-21). Şablon dizisine giren her uç dizesi buradan
    // geçer; DOM'un kendi kaçışını kullanır, elle tablo tutmaz.
    function escText(value) {
        const d = document.createElement('div');
        d.textContent = (value === null || value === undefined) ? '' : String(value);
        return d.innerHTML;
    }

    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

    const TYPE_OPTIONS = {
        // Spec A.1 seçim matrisi: hibritte yalnız oksitleyici devresi anlamlı.
        // Pintle hibritte de MEŞRUDUR (ox-merkezli tek akışkan, v2.5.2).
        hybrid: [
            ['showerhead', 'Showerhead (default)', 'inj.typeShowerheadDefault'],
            ['swirl', 'Pressure-swirl / vortex', 'inj.typeSwirl'],
            ['pintle', 'Pintle (throttleable)', 'inj.typePintle'],
            ['like_impinging', 'Like-impinging (self)', 'inj.typeLike'],
            // V301/H2: tek akışkanlı koaksiyel eleman artık devrede.
            ['coaxial', 'Coaxial (single-fluid: jet + annulus)', 'inj.typeCoaxialSingle'],
        ],
        liquid: [
            ['impinging_doublet', 'Unlike doublet (default)', 'inj.typeDoublet'],
            ['impinging_triplet', 'Unlike triplet (2:1)', 'inj.typeTriplet'],
            ['like_impinging', 'Like-impinging (self)', 'inj.typeLike'],
            ['showerhead', 'Showerhead', 'inj.typeShowerhead'],
            ['pintle', 'Pintle (throttleable)', 'inj.typePintle'],
            ['coax_swirl', 'Coaxial swirl', 'inj.typeCoaxSwirl'],
            ['swirl', 'Pressure-swirl', 'inj.typeSwirlOnly'],
        ],
    };

    // Alan açıklamaları (title): [anahtar, İngilizce yedek]
    const FIELD_HELP_KEYS = {
        inj_type: ['inj.helpType',
            'Injector element family. Drives the geometry model, the '
            + 'discharge-coefficient basis and the atomisation correlation.'],
        inj_dp: ['inj.helpDp',
            'Injector pressure drop as a fraction of chamber pressure. '
            + 'Typical 0.15-0.30; below 0.15 chug instability is likely '
            + '(Sutton & Biblarz 9th ed. Ch. 8; NASA SP-194 Ch. 5-6).'],
        inj_mdot_ox: ['inj.helpMdotOx',
            'Oxidizer mass flow rate through the injector. Typical '
            + 'amateur/university range 0.1-5 kg/s.'],
        inj_mdot_fuel: ['inj.helpMdotFuel',
            'Fuel mass flow rate (liquid engines only). Set by the '
            + 'mixture ratio: mdot_fuel = mdot_ox / (O/F).'],
        inj_pc: ['inj.helpPc',
            'Chamber pressure at the design point. Hybrids typically '
            + '15-40 bar, liquids 30-150 bar.'],
        inj_rho_ox: ['inj.helpRhoOx',
            'Liquid oxidizer density at injection temperature. N2O at '
            + '293 K is about 745-790 kg/m3; LOX about 1141 kg/m3.'],
        inj_rho_fuel: ['inj.helpRhoFuel',
            'Liquid fuel density. RP-1 about 810 kg/m3, ethanol about 789 kg/m3.'],
        inj_inlet: ['inj.helpInlet',
            'Orifice inlet geometry. A radiused inlet (r/d >= 0.15) '
            + 'raises Cd to about 0.90-0.92; a sharp edge gives 0.63-0.84 and '
            + 'can hydraulically flip.'],
        inj_ld: ['inj.helpLd',
            'Orifice length-to-diameter ratio. It selects the discharge '
            + 'coefficient from the circuit C_d table (inlet type and L/D) and '
            + 'the hydraulic-flip verdict. Hybrid: empty means the circuit '
            + 'default L/D = 4 is used and no flip verdict is issued.'],
        inj_n2o: ['inj.helpN2o',
            'Self-pressurised nitrous oxide flashes across the orifice. '
            + 'With this enabled the Dyer NHNE two-phase model sets the flow '
            + 'rate and the pressure drop follows from tank temperature.'],
        inj_tox: ['inj.helpTox',
            'Nitrous oxide tank temperature. Sets saturation pressure '
            + '(about 50 bar at 293 K) and therefore the available dP.'],
        inj_tmr: ['inj.helpTmr',
            'Pintle total momentum ratio target. TMR = 1 gives a 60 deg '
            + 'spray half angle (Cheng 2017); usual band 0.5-2.'],
        // HİBRİT PİNTLE'IN GERÇEK KOLU (2026-08-09 ölçümü).
        // Kullanıcıya 'Pintle TMR target' gösteriliyordu ama hibritte TMR
        // BİR ÇIKTIDIR: aynı akışkan + aynı dP olduğu için hızlar eşittir ve
        // TMR = f/(1-f) bağıntısıyla YALNIZ radyal paydan doğar
        // (hrma/engines/injector_design.py:1660). Çözücünün okuduğu alan
        // `pintle.radial_fraction` idi ve arayüzde HİÇ açılmamıştı, 0,5'te
        // gömülü kalıyordu. Dolayısıyla TMR kutusunu çevirmek sonucu
        // değiştirmiyordu — atıl bir düğmeydi.
        inj_radial_fraction: ['inj.helpRadialFraction',
            'Share of the oxidizer flow sent through the radial tip holes '
            + '(the rest goes through the annulus). This is the real control '
            + 'for a single-fluid hybrid pintle: TMR = f/(1-f) follows from '
            + 'it, and the spray cone angle follows from TMR. Usual band '
            + '0.3-0.7.'],
        inj_bf: ['inj.helpBf',
            'Pintle blockage factor target BF = n·d/(π·D_p): it sets the '
            + 'tip-hole count when neither the hole count nor the hole '
            + 'diameter is given. 0.58 is an HRMA choice (no literature value); '
            + 'the source of the 0.3-0.74 band is not verified.'],
        inj_theta: ['inj.helpTheta',
            'Target spray cone HALF-angle of the swirl elements, met through '
            + 'the Giffen-Muraszew inverse (K -> X -> θ). The solvable envelope '
            + 'is 3.7-71.2 deg: a hybrid design outside it is rejected; the '
            + 'liquid panel clamps it to the envelope with a warning.'],
        // --- V301/E2: hibrit panelin ana tasarımla aynı sözleşmesi ------
        inj_pfeed: ['inj.helpPfeed',
            'Injector inlet pressure P_1 (bar, absolute). Empty: self-'
            + 'pressurised N2O takes P_sat(T_tank), other oxidizers P_c·(1 + '
            + 'dP/P_c). Filled after a calculation only when the main design '
            + 'uses a user-supplied tank pressure.'],
        inj_cd: ['inj.helpCd',
            'Measured discharge coefficient of the orifices. Empty: C_d comes '
            + 'from the circuit table (inlet + L/D). Not applied to swirl '
            + 'elements, whose C_d follows from their geometry.'],
        inj_pin_holes: ['adv.inj.tipSecondaryHoles',
            'Holes drilled through the pintle tip wall, in one row around '
            + 'the post. Radial: hole axes along the radius (classic pintle). '
            + 'Tangential: drilled at an angle to the radius (geometry only; '
            + 'the swirl is not modelled). None: no tip holes - the element '
            + 'becomes a plain annular injector.'],
        inj_pin_dp: ['adv.inj.tipPintleTipDiameter',
            'Outer diameter of the pintle post at its tip (D_p) - the surface '
            + 'the tip holes are drilled into. Empty: sized from the oxidizer '
            + 'flow with the annulus rule t = 0.05·D_p (HRMA choice, no '
            + 'literature value). It sets the annular gap, the hole count '
            + 'through the blockage factor and the default skip distance.'],
        inj_pin_t: ['adv.inj.gapBetweenPintleSleeve',
            'Radial clearance between the pintle post (D_p) and the body bore '
            + '(t) - the annulus the axial oxidizer sheet flows through. '
            + 'Empty: solved from the annulus flow area. If given, it fixes the '
            + 'annulus area and the tip holes take the rest of the flow area.'],
        inj_pin_n: ['adv.inj.tipTipHoleCount',
            'Number of holes in the single circumferential row on the pintle '
            + 'tip (n). Empty: from the blockage factor BF = n·d/(π·D_p) = 0.58 '
            + '(HRMA choice). If given with the hole diameter, the two fix the '
            + 'tip-hole flow area.'],
        inj_pin_d: ['adv.inj.tipTipHoleDiameter',
            'Diameter of each tip hole (d). Empty: solved so the holes carry '
            + 'their share of the oxidizer flow area. Inputs that over-'
            + 'determine the flow (D_p, t, n and d all given and not matching) '
            + 'are rejected with the flow mismatch.'],
        inj_pin_ls: ['adv.inj.distanceFromPintleTip',
            'Axial distance from the annulus exit (body face) to the axis of '
            + 'the tip-hole row (L_s; Dressler & Bauer 2000). Empty: L_s = D_p '
            + '(HRMA choice, no literature value). Geometry and drawing only - '
            + 'no model uses it.'],
        inj_pin_ang: ['adv.inj.tipTangentialAngle',
            'Angle between each hole axis and the local radius (0° = radial, '
            + '90° = tangent). Geometry/CAD only: the tangential momentum and '
            + 'the swirl it induces are NOT modelled; the reported spray angle '
            + 'is the radial value (a lower bound).'],
        inj_pin_od: ['adv.inj.tipBodyOuterDiameter',
            'Outer diameter of the injector body (housing) that surrounds the '
            + 'annulus bore. Empty: HRMA does not size the body (it needs '
            + 'housing material, allowable stress and the pressure across the '
            + 'body wall) and draws only the bore D_p + 2t. If given, the body '
            + 'wall (OD - bore)/2 is checked and drawn; it must fit inside the '
            + 'chamber.'],
        inj_imp_pairs: ['adv.inj.tipElementPairs',
            'Number of like-on-like hole pairs (2 holes each). Empty: the '
            + 'circuit plans the fewest holes whose diameter falls inside the '
            + '0.5-2.5 mm design band, rounded up to an even count. Given '
            + 'alone, the hole diameter is solved from the oxidizer flow; given '
            + 'together with the hole diameter, the two must deliver the target '
            + 'flow within 5%.'],
        inj_imp_d: ['adv.inj.tipImpingementHoleDiameter',
            'Diameter of each doublet hole. Empty: the injector circuit sizes '
            + 'it from the oxidizer flow. If given, the pair count is the '
            + 'nearest whole number for this diameter and the published '
            + 'diameter is the one that delivers the target flow exactly with '
            + 'that count; a plan off by more than 5% is rejected with the '
            + 'nearest valid plans.'],
        inj_imp_angle: ['adv.inj.totalAngleBetweenImpinging',
            'FULL angle 2θ between the two jets of each doublet. It sets the '
            + 'jet direction (axial velocity component) and the drawn '
            + 'impingement geometry; the hole plan does not depend on it. Must '
            + 'lie strictly between 0° and 180°; outside 40-90° a band note is '
            + 'shown (HRMA heuristic threshold; '
            + 'NASA SP-8089 gives 60° as the design value). '
            + 'Empty: 60° (declared).'],
        inj_sw_ds: ['adv.inj.tipSwirlChamberDiameter',
            'Diameter of the swirl (spin) chamber of each element. With the '
            + 'exit orifice diameter d_o it fixes the inlet area that gives the '
            + 'atomizer constant K. Empty: D_s = 2.5·d_o (Lefebvre & McDonell, '
            + 'typical simplex proportion; declared). Below 1.25·d_o the '
            + 'Giffen-Muraszew geometry assumption breaks down and a warning is '
            + 'shown.'],
        inj_sw_nslots: ['adv.inj.tipSlotsPerElement',
            'Number of tangential inlet slots in each swirl element; together '
            + 'they carry the element inlet area A_p = K·D_s·d_o. The element '
            + 'count and the exit orifice come from the injector circuit. '
            + 'Empty: 6 (server default, declared).'],
        inj_sw_w: ['adv.inj.tipSlotWidth',
            'Width of each rectangular tangential slot. Give the width and the '
            + 'height together, or neither. Empty: the slots are sized from the '
            + 'target spray angle (w = 2h, HRMA proportion). If given, the '
            + 'slots fix the atomizer constant K and with it the spray angle.'],
        inj_sw_h: ['adv.inj.tipSlotHeight',
            'Height of each rectangular tangential slot. Give it together with '
            + 'the slot width, or leave both empty.'],
        inj_sh_n: ['inj.helpShHoles',
            'Number of showerhead orifices. Empty: the circuit plans the '
            + 'fewest holes inside the diameter band.'],
        inj_sh_dmin: ['adv.inj.tipMinHoleDiameter',
            'Lower edge of the hole-diameter band the injector circuit plans '
            + 'in. The circuit uses the fewest holes whose diameter falls inside '
            + '[min, max]; a hole count fixed in Injector Design overrides that '
            + 'search. Empty: 0.5 mm (design band 0.5-2.5 mm, Sutton & Biblarz '
            + '9th ed. p. 337; declared).'],
        inj_coax_f: ['adv.inj.tipCoaxialInnerShare',
            'Share of the oxidizer flow through the inner jet; the rest flows '
            + 'through the outer annulus. Both passages carry oxidizer. Empty: '
            + '0.6 (HRMA choice, no literature value; declared). Values outside '
            + '0.1-0.9 are rejected, not clamped.'],
        inj_sh_dmax: ['adv.inj.tipMaxHoleDiameter',
            'Upper edge of the hole-diameter band the injector circuit plans '
            + 'in; it must be larger than the minimum. Empty: 2.5 mm (design '
            + 'band 0.5-2.5 mm, Sutton & Biblarz 9th ed. p. 337; declared).'],
    };

    // V301/L-C: sıvı panelde aynı kimlikli alanların SIVI anlamı (yakıt
    // merkezli pintle, devre başına eleman). Anahtarlar sıvı sayfasının
    // sözlüğünde (i18n_pages.js 'liq.ui.*'); panel yalnız o sayfada sıvıdır.
    const LIQUID_FIELD_HELP_KEYS = {
        inj_n_el: ['liq.ui.total_number_of_injection_element_pairs',
            'Number of injection elements (count) per circuit; like-on-like '
            + 'doublet: same-fluid pairs per circuit. Empty: each circuit '
            + 'plans its own holes.'],
        inj_pin_dp: ['liq.ui.pintle_post_diameter_tip',
            'Outer diameter of the pintle post at its tip (D_p, mm). Empty: '
            + 'sized from the oxidizer flow (t = 0.05·D_p, HRMA choice).'],
        inj_pin_t: ['liq.ui.pintle_annular_gap_tip',
            'Radial gap of the oxidizer annulus (t, mm). Empty: solved from '
            + 'the oxidizer flow area.'],
        inj_pin_n: ['liq.ui.pintle_fuel_hole_count_tip',
            'Number of radial fuel tip holes. Empty: from the blockage factor '
            + '0.58 (HRMA choice).'],
        inj_pin_d: ['liq.ui.pintle_fuel_hole_diameter_tip',
            'Diameter of each radial fuel tip hole (mm). Empty: solved from '
            + 'the fuel flow area.'],
        inj_pin_ls: ['liq.ui.pintle_skip_distance_tip',
            'Skip distance L_s (mm). Empty: L_s = D_p (HRMA choice).'],
        inj_cd: ['inj.helpCdLiquid',
            'Measured discharge coefficient of the orifices, the same '
            + 'quantity as the Discharge Coefficient Cd of the main form. '
            + 'Empty: Cd from the circuit table (inlet + L/D). Not applied to '
            + 'swirl elements, whose Cd follows from their geometry.'],
    };

    function help(id) {
        const pair = (cfg.motorType === 'liquid' && LIQUID_FIELD_HELP_KEYS[id])
            || FIELD_HELP_KEYS[id];
        return pair ? T(pair[0], pair[1]) : '';
    }

    // v3.0.1 N-girdi-2: `title` yalnız fareyle görünür; alanın yanında
    // GÖRÜNÜR "?" ortak bileşenden (field_help.js → HRMAHelp), metin aynı
    // FIELD_HELP_KEYS anahtarından. Bileşen yoksa basılmaz (title kalır).
    function yardimHtml(id) {
        const hk = (cfg.motorType === 'liquid' && LIQUID_FIELD_HELP_KEYS[id])
            || FIELD_HELP_KEYS[id];
        return (hk && window.HRMAHelp && typeof window.HRMAHelp.html === 'function')
            ? window.HRMAHelp.html(hk[0], help(id)) : '';
    }

    function fieldHtml(id, labelKey, label, value, step, extra, ph) {
        const hk = (cfg.motorType === 'liquid' && LIQUID_FIELD_HELP_KEYS[id])
            || FIELD_HELP_KEYS[id];
        const hAttr = hk ? ` data-i18n-title="${hk[0]}" title="${escText(help(id))}"` : '';
        // V301/E2: boş değerli (isteğe bağlı) alanın yer tutucusu da
        // çeviriden gelir; değer yoksa ``value`` niteliği BASILMAZ.
        const vAttr = (value === '' || value == null) ? '' : ` value="${value}"`;
        const pAttr = ph ? ` data-i18n-placeholder="${ph[0]}" placeholder="${escText(T(ph[0], ph[1]))}"` : '';
        return `<div class="form-group" ${extra || ''}${hAttr}>
            <label><span data-i18n="${labelKey}">${T(labelKey, label)}</span>${yardimHtml(id)}</label>
            <input type="number" id="${id}"${vAttr} step="${step}"${hAttr}${pAttr}>
        </div>`;
    }

    // ------------------------------------------------------------------
    // V301/E2 — HİBRİT PANEL ⟷ ANA TASARIM SÖZLEŞMESİ
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ayberk1/enjektor-genel/
    // once_en_ekran.json): ana tasarımda pintle seçili ve motor ṁ_ox
    // 0,40 kg/s iken bu panel hesaptan sonra da 'Showerhead (default)',
    // ṁ_ox 2 kg/s ve duş başlığı şeması gösteriyordu. Kök neden:
    // resultsProvider yalnız BOŞ alanı dolduruyordu (fillIfEmpty) ve
    // hibrit panelin alanları dolu doğuyordu (2,0 / 20 / 786) — sağlayıcı
    // hiç yazamıyordu; tip ise hiç eşlenmiyordu. Artık hesaptan sonra
    // panel ana tasarımın devre girdilerini (tip, ṁ_ox, Pc, ρ_ox, T_tank,
    // L/D, ΔP/Pc, P₁, Cd ve eleman girdileri) ALIR ve bir kez koşar: aynı
    // girdiler aynı çözücüden (/api/injector-design) aynı sayıları verir.
    // Panelin rolü "bağımsız ne-olur hesaplayıcısı"dır: alanlar sonradan
    // değiştirilebilir, ana tasarım değişmez (rol notu panelde yazar).

    //: Ana formun tip sözcüğü -> panelin (devre modülünün) tip sözcüğü.
    //: V301/H2: 'coaxial' artık devrede (tek akışkanlı koaksiyel eleman,
    //: ``design_coaxial_element``); panel aynı ada eşler.
    const MAIN_TO_PANEL = {
        showerhead: 'showerhead', impingement: 'like_impinging',
        pintle: 'pintle', swirl: 'swirl', coaxial: 'coaxial',
    };

    //: Panel alanı -> değer anahtarı (engineValuesFromResults çıktısı).
    //: Pintle/çarpışmalı/swirl/duş başlığı eleman alanları ana formun istek
    //: adlarını taşır; yük (spec) adlarına çevirisi ``specFromValues``ta.
    const HYBRID_VALUE_FIELDS = [
        ['inj_mdot_ox', 'mdot_ox'], ['inj_pc', 'Pc_bar'],
        ['inj_rho_ox', 'rho_ox'], ['inj_dp', 'dp_ratio'],
        ['inj_ld', 'l_over_d'], ['inj_tox', 'T_ox_K'],
        ['inj_pfeed', 'p_feed_bar'], ['inj_cd', 'cd'],
        ['inj_pin_dp', 'pintle_diameter'], ['inj_pin_t', 'annular_gap'],
        ['inj_pin_n', 'pintle_radial_hole_count'],
        ['inj_pin_d', 'pintle_radial_hole_diameter'],
        ['inj_pin_ls', 'skip_distance'], ['inj_pin_ang', 'pintle_tangential_angle'],
        ['inj_pin_od', 'outer_diameter'],
        ['inj_imp_pairs', 'element_pairs'], ['inj_imp_d', 'orifice_diameter'],
        ['inj_imp_angle', 'impingement_angle'],
        ['inj_theta', 'swirl_angle'], ['inj_sw_ds', 'swirl_chamber_diameter'],
        ['inj_sw_nslots', 'n_slots'], ['inj_sw_w', 'slot_width'],
        ['inj_sw_h', 'slot_height'],
        ['inj_sh_n', 'n_holes'], ['inj_sh_dmin', 'hole_diameter_min'],
        ['inj_sh_dmax', 'hole_diameter_max'],
        ['inj_coax_f', 'coaxial_inner_flow_fraction'],
    ];

    function sayiMi(v) { return typeof v === 'number' && isFinite(v); }

    //: Ana formdan (istek gövdesi) panele taşınan eleman girdileri — ad
    //: ana istekle AYNI (``_eleman_istek_ezmeleri`` / pintle kapısı).
    const MAIN_ELEMENT_FIELDS = {
        pintle: ['pintle_diameter', 'annular_gap', 'pintle_radial_hole_count',
                 'pintle_radial_hole_diameter', 'skip_distance',
                 'pintle_tangential_angle', 'outer_diameter'],
        like_impinging: ['element_pairs', 'orifice_diameter',
                         'impingement_angle'],
        swirl: ['swirl_angle', 'swirl_chamber_diameter', 'n_slots',
                'slot_width', 'slot_height'],
        showerhead: ['n_holes', 'hole_diameter_min', 'hole_diameter_max'],
    };

    /**
     * /calculate yanıtı (+ isteğin kendisi) -> panelin alan değerleri.
     *
     * Sayılar devrenin KENDİ yapraklarından okunur, yeniden hesaplanmaz:
     *   ṁ_ox   : injector_design_detail.ox_circuit.mdot_kg_s
     *   Pc     : motor.chamber_pressure
     *   ρ_ox   : kullanıcı tank kipinde injector_design.inlet_state.
     *            liquid_density_kg_m3; aksi hâlde devrenin süreklilik
     *            özdeşliği ρ = ṁ/(v·A) (devre hızı tam bu bağıntıyla
     *            yayımlar — manifold.v_ratio_basis aynı özdeşliği yazar)
     *   T_tank : motor.oxidizer_inlet_state.temperature_K
     *   ΔP/Pc  : ox_circuit.dp_pc_ratio; L/D: ox_circuit.l_over_d (yalnız
     *            KAZANILMIŞSA — plaka kalınlığı verilmediyse boş kalır ve
     *            panel de devrenin beyanlı varsayılanını kullanır)
     *   P₁     : yalnız kullanıcı tank basıncı kipinde feed_pressure_bar
     *   Cd     : yalnız kullanıcı Cd'si UYGULANDIYSA
     * Eleman girdileri isteğin kendisinden (kullanıcının verdiği, boşsa boş).
     * Devre çözümü yoksa (not_analyzed) null döner.
     */
    function engineValuesFromResults(results, request) {
        if (!results || typeof results !== 'object') return null;
        if (!results.motor && results.injection_system) {
            return liquidValuesFromResults(results);
        }
        const m = results.motor || {};
        const ozet = m.injector_design || {};
        const det = m.injector_design_detail || {};
        const oxc = det.ox_circuit || {};
        if (ozet.status === 'not_analyzed' || !det.ox_circuit) return null;
        const istek = (request && typeof request === 'object') ? request : {};
        const tip = MAIN_TO_PANEL[ozet.injector_type || istek.injector_type];
        if (!tip) return null;
        const v = { injector_type: tip };
        v.mdot_ox = sayiMi(oxc.mdot_kg_s) ? oxc.mdot_kg_s : m.mdot_ox;
        v.Pc_bar = m.chamber_pressure;
        const giris = ozet.inlet_state || {};
        if (sayiMi(giris.liquid_density_kg_m3)) {
            v.rho_ox = giris.liquid_density_kg_m3;
        } else if (sayiMi(oxc.velocity_m_s) && sayiMi(oxc.total_area_mm2)
                   && oxc.velocity_m_s > 0 && oxc.total_area_mm2 > 0) {
            v.rho_ox = v.mdot_ox / (oxc.velocity_m_s * oxc.total_area_mm2 * 1e-6);
        }
        v.n2o = (oxc.flow_model === 'NHNE')
            || String(istek.oxidizer_type || '').toLowerCase() === 'n2o';
        const durum = m.oxidizer_inlet_state || {};
        v.T_ox_K = sayiMi(durum.temperature_K) ? durum.temperature_K : null;
        v.dp_ratio = sayiMi(oxc.dp_pc_ratio) ? oxc.dp_pc_ratio : null;
        const ldKazanildi = !/module default/i.test(String(oxc.l_over_d_basis || ''));
        v.l_over_d = (ldKazanildi && sayiMi(oxc.l_over_d)) ? oxc.l_over_d : null;
        v.p_feed_bar = (ozet.tank_pressure_source === 'user'
                        && sayiMi(ozet.feed_pressure_bar))
            ? ozet.feed_pressure_bar : null;
        const cdIn = ozet.discharge_coefficient_input;
        v.cd = (cdIn && cdIn.applied === true && sayiMi(cdIn.value)) ? cdIn.value : null;
        // Swirl: teğet yuva sayısı devrenin KENDİ sayısıdır (istek vermediyse
        // ucun beyanlı varsayılanı devreye de gitti) — panel aynı sayıyı alır.
        const swg = det.swirl_geometry || {};
        if (tip === 'pintle') {
            v.secondary_holes = istek.secondary_holes || null;
        }
        (MAIN_ELEMENT_FIELDS[tip] || []).forEach(function (ad) {
            v[ad] = sayiMi(istek[ad]) ? istek[ad] : null;
        });
        if (tip === 'swirl' && v.n_slots == null && sayiMi(swg.tangential_inlets)) {
            v.n_slots = swg.tangential_inlets;
        }
        // V301/H2: koaksiyelde iç jet payı devrenin KENDİ sayısıdır (istek
        // payı, eski çap çiftinin payı ya da beyanlı varsayılan — hangisi
        // devreye girdiyse); panel aynı sayıyla aynı elemanı çözer.
        if (tip === 'coaxial') {
            const cg = det.coaxial_geometry || {};
            v.coaxial_inner_flow_fraction = sayiMi(cg.inner_flow_fraction)
                ? cg.inner_flow_fraction : null;
        }
        v.T_c_K = sayiMi(m.chamber_temperature) ? m.chamber_temperature : null;
        v.mw_gas = sayiMi(m.molecular_weight) ? m.molecular_weight : null;
        return v;
    }

    /**
     * V301/L-C — /calculate_liquid yanıtı -> sıvı panelin alan değerleri.
     *
     * Sayılar motorun devreyi ÇÖZDÜĞÜ girdiden okunur, yeniden türetilmez:
     * ``injection_system.circuit_request.spec`` (motorun design_injector /
     * design_like_doublet çağrısının yükü) ve ``user_discharge_coefficient``
     * (kullanıcı Cd'si; motorla aynı uygulanır). Devre çözümü yoksa ya da
     * gaz-gaz ana oda enjeksiyonuysa (FFSC; panel o devreyi kuramaz) null.
     */
    function liquidValuesFromResults(r) {
        const inj = r.injection_system || {};
        const det = inj.injector_design_detail || {};
        const cr = inj.circuit_request || {};
        const sp = cr.spec;
        if (!sp || typeof sp !== 'object' || det.status !== 'success'
                || sp.injector_type === 'gas_gas_coaxial') return null;
        const v = { motor_type: 'liquid', injector_type: sp.injector_type };
        ['mdot_ox', 'mdot_fuel', 'Pc_bar', 'rho_ox', 'rho_fuel', 'T_c_K',
         'mw_gas', 'mu_ox', 'mu_fuel'].forEach(function (k) {
            v[k] = sayiMi(sp[k]) ? sp[k] : null;
        });
        v.dp_ratio = sayiMi(sp.dp_ratio_ox) ? sp.dp_ratio_ox : null;
        v.dp_ratio_fuel = sayiMi(sp.dp_ratio_fuel) ? sp.dp_ratio_fuel : null;
        v.fluid_ox = (typeof sp.fluid_ox === 'string') ? sp.fluid_ox : null;
        v.fluid_fuel = (typeof sp.fluid_fuel === 'string') ? sp.fluid_fuel : null;
        v.cd = sayiMi(cr.user_discharge_coefficient)
            ? cr.user_discharge_coefficient : null;
        const imp = sp.impingement || {};
        v.n_elements = sayiMi(imp.pairs) ? imp.pairs
            : (sayiMi(sp.n_orifices_ox) ? sp.n_orifices_ox : null);
        const pin = sp.pintle || {};
        [['d_pintle_mm', 'pintle_diameter'], ['annulus_gap_mm', 'annular_gap'],
         ['n_radial_holes', 'pintle_radial_hole_count'],
         ['radial_hole_d_mm', 'pintle_radial_hole_diameter'],
         ['skip_distance_mm', 'skip_distance']].forEach(function (p) {
            v[p[1]] = sayiMi(pin[p[0]]) ? pin[p[0]] : null;
        });
        return v;
    }

    //: Sıvı panel alanı -> değer anahtarı (liquidValuesFromResults çıktısı).
    const LIQUID_VALUE_FIELDS = [
        ['inj_mdot_ox', 'mdot_ox'], ['inj_mdot_fuel', 'mdot_fuel'],
        ['inj_pc', 'Pc_bar'], ['inj_rho_ox', 'rho_ox'],
        ['inj_rho_fuel', 'rho_fuel'], ['inj_dp', 'dp_ratio'],
        ['inj_ld', 'l_over_d'], ['inj_cd', 'cd'], ['inj_n_el', 'n_elements'],
        ['inj_pin_dp', 'pintle_diameter'], ['inj_pin_t', 'annular_gap'],
        ['inj_pin_n', 'pintle_radial_hole_count'],
        ['inj_pin_d', 'pintle_radial_hole_diameter'],
        ['inj_pin_ls', 'skip_distance'],
    ];

    /**
     * V301/L-C — sıvı panel değerleri -> /api/injector-design yükü. Motorun
     * devre yüküyle AYNI anahtarlar; boş (null) alan yüke KONMAZ.
     */
    function liquidSpecFromValues(v) {
        const spec = { motor_type: 'liquid', injector_type: v.injector_type,
                       mdot_ox: v.mdot_ox, mdot_fuel: v.mdot_fuel,
                       Pc_bar: v.Pc_bar };
        ['rho_ox', 'rho_fuel', 'T_c_K', 'mw_gas', 'mu_ox', 'mu_fuel', 'cd',
         'l_over_d'].forEach(function (k) {
            if (sayiMi(v[k])) spec[k] = v[k];
        });
        if (sayiMi(v.dp_ratio)) {
            spec.dp_ratio_ox = v.dp_ratio;
            spec.dp_ratio_fuel = sayiMi(v.dp_ratio_fuel) ? v.dp_ratio_fuel
                : v.dp_ratio;
        }
        if (v.fluid_ox) spec.fluid_ox = v.fluid_ox;
        if (v.fluid_fuel) spec.fluid_fuel = v.fluid_fuel;
        if (v.inlet && v.inlet !== 'sharp') {
            spec.inlet_ox = v.inlet;
            spec.inlet_fuel = v.inlet;
        }
        const t = v.injector_type;
        if (sayiMi(v.n_elements) && t !== 'pintle') {
            if (t === 'like_impinging') {
                spec.impingement = { pairs: v.n_elements };
            } else {
                spec.n_orifices_ox = v.n_elements;
                spec.n_orifices_fuel = v.n_elements;
            }
        }
        if (t === 'pintle') {
            const pin = {};
            [['pintle_diameter', 'd_pintle_mm'], ['annular_gap', 'annulus_gap_mm'],
             ['pintle_radial_hole_count', 'n_radial_holes'],
             ['pintle_radial_hole_diameter', 'radial_hole_d_mm'],
             ['skip_distance', 'skip_distance_mm'],
             ['bf_target', 'bf_target'], ['tmr_target', 'tmr_target']].forEach(function (p) {
                if (sayiMi(v[p[0]])) pin[p[1]] = v[p[0]];
            });
            if (Object.keys(pin).length) spec.pintle = pin;
        }
        if ((t === 'swirl' || t === 'coax_swirl') && sayiMi(v.theta_target_deg)) {
            spec.swirl = { theta_target_deg: v.theta_target_deg };
        }
        return spec;
    }

    /**
     * Panel değerleri (hibrit) -> /api/injector-design yükü. buildSpec()
     * hibritte BUNU çağırır; düğüm testleri aynı işlevi kullanır. Boş
     * (null) alan yüke KONMAZ — çözücü kendi beyanlı varsayılanını uygular.
     */
    function specFromValues(v) {
        if (v && v.motor_type === 'liquid') return liquidSpecFromValues(v);
        const spec = { motor_type: 'hybrid', injector_type: v.injector_type,
                       mdot_ox: v.mdot_ox, Pc_bar: v.Pc_bar,
                       inlet_ox: v.inlet_ox || 'sharp' };
        if (sayiMi(v.rho_ox)) spec.rho_ox = v.rho_ox;
        if (v.n2o) {
            spec.fluid_ox = 'n2o';
            spec.T_ox_K = sayiMi(v.T_ox_K) ? v.T_ox_K : 293.15;
        } else {
            spec.fluid_ox = 'generic';
            if (sayiMi(v.dp_ratio)) spec.dp_ratio_ox = v.dp_ratio;
        }
        if (sayiMi(v.l_over_d)) spec.l_over_d = v.l_over_d;
        if (sayiMi(v.p_feed_bar)) spec.p_feed_bar = v.p_feed_bar;
        if (sayiMi(v.cd)) spec.cd = v.cd;
        if (sayiMi(v.T_c_K)) spec.T_c_K = v.T_c_K;
        if (sayiMi(v.mw_gas)) spec.mw_gas = v.mw_gas;
        const t = v.injector_type;
        if (t === 'pintle') {
            const pin = {};
            if (v.secondary_holes) pin.secondary_holes = v.secondary_holes;
            [['pintle_diameter', 'd_pintle_mm'], ['annular_gap', 'annulus_gap_mm'],
             ['pintle_radial_hole_count', 'n_radial_holes'],
             ['pintle_radial_hole_diameter', 'radial_hole_d_mm'],
             ['skip_distance', 'skip_distance_mm'],
             ['pintle_tangential_angle', 'tangential_angle_deg'],
             ['outer_diameter', 'housing_outer_diameter_mm']].forEach(function (p) {
                if (sayiMi(v[p[0]])) pin[p[1]] = v[p[0]];
            });
            if (sayiMi(v.radial_fraction)) pin.radial_fraction = v.radial_fraction;
            if (sayiMi(v.bf_target)) pin.bf_target = v.bf_target;
            spec.pintle = pin;
        } else if (t === 'like_impinging') {
            const imp = {};
            [['element_pairs', 'pairs'], ['orifice_diameter', 'hole_d_mm'],
             ['impingement_angle', 'full_angle_deg']].forEach(function (p) {
                if (sayiMi(v[p[0]])) imp[p[1]] = v[p[0]];
            });
            if (Object.keys(imp).length) spec.impingement = imp;
        } else if (t === 'swirl') {
            const sw = {};
            [['swirl_angle', 'theta_target_deg'], ['swirl_chamber_diameter', 'chamber_d_mm'],
             ['n_slots', 'n_inlets'], ['slot_width', 'slot_w_mm'],
             ['slot_height', 'slot_h_mm']].forEach(function (p) {
                if (sayiMi(v[p[0]])) sw[p[1]] = v[p[0]];
            });
            if (Object.keys(sw).length) spec.swirl = sw;
        } else if (t === 'showerhead') {
            if (sayiMi(v.n_holes)) spec.n_orifices_ox = v.n_holes;
            const kisit = {};
            if (sayiMi(v.hole_diameter_min)) kisit.d_min_mm = v.hole_diameter_min;
            if (sayiMi(v.hole_diameter_max)) kisit.d_max_mm = v.hole_diameter_max;
            if (Object.keys(kisit).length) spec.orifice_constraints = kisit;
        } else if (t === 'coaxial') {
            if (sayiMi(v.coaxial_inner_flow_fraction)) {
                spec.coaxial = { inner_flow_fraction: v.coaxial_inner_flow_fraction };
            }
        }
        return spec;
    }

    function panelHtml(motorType) {
        const isHybrid = motorType === 'hybrid';
        const typeOpts = (TYPE_OPTIONS[motorType] || TYPE_OPTIONS.liquid)
            .map(([v, t, k]) => `<option value="${v}" data-i18n="${k}">${T(k, t)}</option>`).join('');
        return `
        <div class="panel" id="injectorPanel" style="width:100%; grid-column: 1 / -1;">
            <h2><span data-i18n="inj.title">${T('inj.title', 'Injector Design')}</span> — <span
                data-i18n="${isHybrid ? 'inj.subHybrid' : 'inj.subLiquid'}">${isHybrid
                ? T('inj.subHybrid', 'HYBRID (oxidizer circuit only)')
                : T('inj.subLiquid', 'LIQUID (bipropellant)')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatItDoes">${T('common.whatItDoes',
                    'What it does:')}</strong>
                <span data-i18n="inj.intro">${T('inj.intro',
                    'Orifice sizing (mdot = Cd·A·sqrt(2·rho·dP)), Dyer NHNE two-phase '
                    + 'model for N2O, element-specific geometry (impingement angle and '
                    + 'momentum, pintle TMR/BF, swirl K to cone angle), SMD atomisation '
                    + 'estimate, manifold sizing and chug stability checks. '
                    + 'Sources: NASA SP-8089, Dyer 2007, Lefebvre.')}</span>
            </div>
            ${isHybrid ? `<div id="inj_role_note" class="help-text" data-i18n="inj.roleWhatIf"
                 style="margin:6px 0 0; font-size:0.8rem; color:var(--hd-ink-dim);">${T('inj.roleWhatIf',
                'Independent what-if calculator. After each main calculation it is filled from '
                + 'the injector circuit of that design (same type, oxidizer flow, chamber pressure, '
                + 'density, tank temperature, L/D, pressure drop and element inputs) and run once, '
                + 'so it shows the circuit numbers of the design above. Change any field to explore '
                + 'an alternative; the main design is not changed.')}</div>`
                : `<div id="inj_role_note" class="help-text" data-i18n="inj.roleWhatIfLiquid"
                 style="margin:6px 0 0; font-size:0.8rem; color:var(--hd-ink-dim);">${T('inj.roleWhatIfLiquid',
                'Independent what-if calculator. After each main calculation it is filled from '
                + 'the injector circuit of that design (same type, fuel and oxidizer flows, chamber '
                + 'pressure, densities, pressure drop, discharge coefficient, element count and '
                + 'pintle dimensions) and run once, so it shows the circuit numbers of the design '
                + 'above. Change any field to explore an alternative; the main design is not '
                + 'changed.')}</div>`}
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:10px; margin:12px 0;">
                <div class="form-group" data-i18n-title="inj.helpType" title="${help('inj_type')}">
                    <label><span data-i18n="inj.fType">${T('inj.fType', 'Injector type')}</span>${yardimHtml('inj_type')}</label>
                    <select id="inj_type" data-i18n-title="inj.helpType"
                        title="${help('inj_type')}">${typeOpts}</select>
                </div>
                ${fieldHtml('inj_dp', 'inj.fDp', 'dP / Pc ratio', 0.20, 0.01)}
                ${fieldHtml('inj_mdot_ox', 'inj.fMdotOx', 'Oxidizer mdot (kg/s)', 2.0, 0.05)}
                ${isHybrid ? fieldHtml('inj_pfeed', 'inj.fPfeed', 'Inlet pressure P1 (bar)', '', 0.1,
                                       '', ['inj.phPfeed', 'from tank state']) : ''}
                ${fieldHtml('inj_cd', 'inj.fCd', 'Measured C_d (-)', '', 0.01,
                            '', ['inj.phCd', 'circuit table'])}
                ${isHybrid ? '' : fieldHtml('inj_mdot_fuel', 'inj.fMdotFuel', 'Fuel mdot (kg/s)', 0.8, 0.05)}
                ${fieldHtml('inj_pc', 'inj.fPc', 'Chamber pressure (bar)', isHybrid ? 20 : 100, 1)}
                ${fieldHtml('inj_rho_ox', 'inj.fRhoOx', 'Oxidizer density (kg/m3)', isHybrid ? 786 : 1141, 5)}
                ${isHybrid ? '' : fieldHtml('inj_rho_fuel', 'inj.fRhoFuel', 'Fuel density (kg/m3)', 810, 5)}
                <div class="form-group" data-i18n-title="inj.helpInlet" title="${help('inj_inlet')}">
                    <label><span data-i18n="inj.fInlet">${T('inj.fInlet', 'Orifice inlet')}</span>${yardimHtml('inj_inlet')}</label>
                    <select id="inj_inlet" data-i18n-title="inj.helpInlet" title="${help('inj_inlet')}">
                        <option value="sharp" data-i18n="inj.inletSharp">${
                            T('inj.inletSharp', 'Sharp edge')}</option>
                        <option value="radiused" data-i18n="inj.inletRadiused">${
                            T('inj.inletRadiused', 'Radiused')}</option>
                    </select>
                </div>
                ${isHybrid
                    ? fieldHtml('inj_ld', 'inj.fLd', 'Orifice L/D', '', 0.5, '',
                                ['inj.phLd', 'default 4'])
                    // V301/L-C: sıvıda da boş doğar — motor L/D göndermez,
                    // devre kendi beyanlı varsayılanını (4) kullanır.
                    : fieldHtml('inj_ld', 'inj.fLd', 'Orifice L/D', '', 0.5, '',
                                ['inj.phLd', 'default 4'])}
                ${isHybrid ? `
                <div class="form-group" id="inj_n2o_group" data-i18n-title="inj.helpN2o"
                     title="${help('inj_n2o')}">
                    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                        <input type="checkbox" id="inj_n2o" checked style="width:auto;"
                            data-i18n-title="inj.helpN2o" title="${help('inj_n2o')}">
                        <span data-i18n="inj.fN2o">${T('inj.fN2o', 'N2O two-phase (Dyer NHNE)')}</span>${yardimHtml('inj_n2o')}
                    </label>
                </div>
                ${fieldHtml('inj_tox', 'inj.fTox', 'N2O tank temperature (K)', 293, 1)}` : ''}
                ${isHybrid
                    // Hibritte kullanıcının çevirebileceği GERÇEK kol radyal
                    // paydır; TMR onun çıktısıdır (yukarıdaki nota bakın).
                    ? fieldHtml('inj_radial_fraction', 'inj.fRadialFraction',
                                'Radial flow fraction (0-1)', 0.5, 0.05,
                                'id="inj_radial_fraction_group"')
                    : fieldHtml('inj_tmr', 'inj.fTmr', 'Pintle TMR target', 1.0, 0.05,
                                'id="inj_tmr_group"')}
                ${fieldHtml('inj_bf', 'inj.fBf', 'Pintle BF target', 0.58, 0.02, 'id="inj_bf_group"')}
                ${isHybrid
                    ? fieldHtml('inj_theta', 'inj.fTheta', 'Swirl cone half angle target (deg)', '', 1,
                                'id="inj_theta_group"', ['inj.phAngle45', '45° if empty'])
                    : fieldHtml('inj_theta', 'inj.fTheta', 'Swirl cone half angle target (deg)', 45, 1,
                                'id="inj_theta_group"')}
                ${isHybrid ? hybridElementFields() : liquidElementFields()}
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="inj_run" data-i18n="inj.btnRun">${
                        T('inj.btnRun', 'Design injector')}</button>
                </div>
            </div>
            <div id="inj_dp_note" style="font-size:0.78rem; color:var(--hd-ink-dim);
                 margin:-4px 0 8px;"></div>
            <div id="inj_sync_note" style="font-size:0.78rem; color:var(--hd-ink-dim);
                 margin:-4px 0 8px;"></div>
            <div id="inj_tmr_note" style="font-size:0.78rem; color:var(--hd-orange, #ff8c33);
                 margin:-4px 0 8px;"></div>
            <div id="inj_schematic" style="margin:10px 0; padding:8px;
                 border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                 border-radius:8px; max-width:520px;"></div>
            <div id="inj_status" style="font-family:var(--hd-mono); color:var(--hd-ink-dim); margin:6px 0;"></div>
            <div id="inj_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="inj_results" style="display:none;"></div>
        </div>`;
    }

    // V301/E2 — hibrit eleman alanları (ana formla AYNI ölçüler, AYNI
    // ipuçları; boş = devre boyutlandırır). Tipe göre görünürlük
    // syncTypeFields'ta.
    function hybridElementFields() {
        const solver = ['inj.phSolver', 'solver sizes'];
        const g = (grp) => `data-inj-group="${grp}"`;
        const holes = `<div class="form-group" data-inj-group="pintle" data-i18n-title="adv.inj.tipSecondaryHoles"
                 title="${escText(help('inj_pin_holes'))}">
                <label><span data-i18n="adv.inj.secondaryHoles">${T('adv.inj.secondaryHoles', 'Secondary Holes')}</span>${yardimHtml('inj_pin_holes')}</label>
                <select id="inj_pin_holes" data-i18n-title="adv.inj.tipSecondaryHoles" title="${escText(help('inj_pin_holes'))}">
                    <option value="none" data-i18n="adv.inj.none">${T('adv.inj.none', 'None')}</option>
                    <option value="radial" selected data-i18n="adv.inj.radialHoles">${T('adv.inj.radialHoles', 'Radial Holes')}</option>
                    <option value="tangential" data-i18n="adv.inj.tangentialHoles">${T('adv.inj.tangentialHoles', 'Tangential Holes')}</option>
                </select>
            </div>`;
        return holes
            + fieldHtml('inj_pin_dp', 'adv.inj.pintleTipDiameterMm', 'Pintle Tip Diameter D_p (mm)', '', 'any', g('pintle'), solver)
            + fieldHtml('inj_pin_t', 'adv.inj.annularGapMm', 'Annular Gap t (mm)', '', 'any', g('pintle'), solver)
            + fieldHtml('inj_pin_n', 'adv.inj.tipHoleCount', 'Tip Hole Count n', '', 1, g('pintle'), solver)
            + fieldHtml('inj_pin_d', 'adv.inj.tipHoleDiameterMm', 'Tip Hole Diameter d (mm)', '', 'any', g('pintle'), solver)
            + fieldHtml('inj_pin_ls', 'adv.inj.skipDistanceMm', 'Skip Distance L_s (mm)', '', 'any', g('pintle'), solver)
            + fieldHtml('inj_pin_ang', 'adv.inj.tangentialAngleDeg', 'Tangential Hole Angle (deg)', '', 'any',
                        g('pintle-tangential'), ['inj.phNotSized', 'not sized'])
            + fieldHtml('inj_pin_od', 'adv.inj.outerDiameterMm', 'Injector Body Outer Diameter (mm)', '', 'any',
                        g('pintle'), ['inj.phNotSized', 'not sized'])
            + fieldHtml('inj_imp_pairs', 'adv.inj.numberElementPairs', 'Number of Doublet Pairs', '', 1, g('like_impinging'), solver)
            + fieldHtml('inj_imp_d', 'adv.inj.orificeDiameterMm', 'Hole Diameter d (mm)', '', 'any', g('like_impinging'), solver)
            + fieldHtml('inj_imp_angle', 'adv.inj.impingementAngleDegrees', 'Impingement Angle 2θ (deg)', '', 'any',
                        g('like_impinging'), ['inj.phAngle60', '60° if empty'])
            + fieldHtml('inj_sw_ds', 'adv.inj.swirlChamberDiameterMm', 'Swirl Chamber Diameter D_s (mm)', '', 'any',
                        g('swirl'), ['inj.phChamber', '2.5·d_o if empty'])
            + fieldHtml('inj_sw_nslots', 'adv.inj.numberTangentialSlots', 'Tangential Slots per Element', '', 1,
                        g('swirl'), ['inj.phServerDefault', 'server default'])
            + fieldHtml('inj_sw_w', 'adv.inj.slotWidthMm', 'Slot Width w (mm)', '', 0.1, g('swirl'), solver)
            + fieldHtml('inj_sw_h', 'adv.inj.slotHeightMm', 'Slot Height h (mm)', '', 0.1, g('swirl'), solver)
            + fieldHtml('inj_sh_n', 'inj.fShHoles', 'Number of holes', '', 1, g('showerhead'), solver)
            + fieldHtml('inj_sh_dmin', 'adv.inj.minHoleDiameterMm', 'Min Hole Diameter (mm)', '', 0.1,
                        g('showerhead'), ['inj.phServerDefault', 'server default'])
            + fieldHtml('inj_sh_dmax', 'adv.inj.maxHoleDiameterMm', 'Max Hole Diameter (mm)', '', 0.1,
                        g('showerhead'), ['inj.phServerDefault', 'server default'])
            + fieldHtml('inj_coax_f', 'adv.inj.coaxialInnerShare', 'Inner Jet Flow Share (0.1-0.9)',
                        '', 0.05, g('coaxial'), ['adv.ph.coaxialShareDefault',
                                                 '0.6 if empty (declared)']);
    }

    // V301/L-C — sıvı eleman alanları (ana formla AYNI ölçüler, sıvı
    // sayfasının ipuçları; boş = devre boyutlandırır).
    function liquidElementFields() {
        const solver = ['liq.ui.ph_solver_sizes', 'solver sizes'];
        const g = (grp) => `data-inj-group="${grp}"`;
        return fieldHtml('inj_n_el', 'liq.ui.number_of_injector_elements',
                         'Number of Injector Elements', '', 1, g('liq-elements'), solver)
            + fieldHtml('inj_pin_dp', 'liq.ui.pintle_post_diameter', 'Pintle Post Diameter D_p (mm)', '', 'any', g('pintle'), solver)
            + fieldHtml('inj_pin_t', 'liq.ui.pintle_annular_gap', 'Oxidizer Annular Gap t (mm)', '', 'any', g('pintle'), solver)
            + fieldHtml('inj_pin_n', 'liq.ui.pintle_fuel_hole_count', 'Fuel Tip Hole Count n', '', 1, g('pintle'), solver)
            + fieldHtml('inj_pin_d', 'liq.ui.pintle_fuel_hole_diameter', 'Fuel Tip Hole Diameter d (mm)', '', 'any', g('pintle'), solver)
            + fieldHtml('inj_pin_ls', 'liq.ui.pintle_skip_distance', 'Skip Distance L_s (mm)', '', 'any', g('pintle'),
                        ['liq.ui.ph_ls_equals_dp', 'L_s = D_p if empty']);
    }

    function readLiquidValues() {
        const v = { motor_type: 'liquid',
                    injector_type: document.getElementById('inj_type').value };
        LIQUID_VALUE_FIELDS.forEach(function (f) {
            const el = document.getElementById(f[0]);
            if (!el) return;
            const raw = String(el.value == null ? '' : el.value).trim();
            v[f[1]] = raw === '' ? null : parseFloat(raw);
        });
        const inl = document.getElementById('inj_inlet');
        v.inlet = inl ? inl.value : 'sharp';
        const gizli = cfg._liq || {};
        ['T_c_K', 'mw_gas', 'mu_ox', 'mu_fuel', 'fluid_ox', 'fluid_fuel',
         'dp_ratio_fuel'].forEach(function (k) {
            if (gizli[k] != null) v[k] = gizli[k];
        });
        // ΔP/Pc alanı elle değiştirildiyse iki devre de o oranı alır.
        if (sayiMi(v.dp_ratio) && sayiMi(gizli.dp_ratio)
                && v.dp_ratio !== gizli.dp_ratio) v.dp_ratio_fuel = v.dp_ratio;
        if (v.injector_type === 'pintle') v.n_elements = null;
        return v;
    }

    function writeLiquidValues(v) {
        LIQUID_VALUE_FIELDS.forEach(function (f) {
            const el = document.getElementById(f[0]);
            if (!el) return;
            const x = v[f[1]];
            el.value = sayiMi(x) ? String(x) : '';
        });
        const inl = document.getElementById('inj_inlet');
        if (inl) inl.value = 'sharp';
        cfg._liq = { T_c_K: v.T_c_K, mw_gas: v.mw_gas, mu_ox: v.mu_ox,
                     mu_fuel: v.mu_fuel, fluid_ox: v.fluid_ox,
                     fluid_fuel: v.fluid_fuel, dp_ratio: v.dp_ratio,
                     dp_ratio_fuel: v.dp_ratio_fuel };
    }

    function badge(text, kind, title) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)', warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)', info: 'var(--hd-cyan, #00e5ff)',
        };
        const c = colors[kind] || colors.info;
        return `<span title="${title || ''}" style="border:1px solid ${c}; color:${c};
                 border-radius:6px; padding:4px 10px; font-family:var(--hd-mono);
                 font-size:0.75rem;">${text}</span>`;
    }

    function num(id, fallback) {
        const el = document.getElementById(id);
        if (!el) return fallback;
        const v = parseFloat(el.value);
        return Number.isFinite(v) ? v : fallback;
    }

    // Alan BOŞSA doldurur; kullanıcı bir değer girdiyse ASLA ezmez.
    // (Eski davranış her çalıştırmada elle girilen değeri siliyordu.)
    function fmt(x, d) {
        return (x == null || !Number.isFinite(x)) ? '—' : x.toFixed(d == null ? 2 : d);
    }

    // ------------------------------------------------------------------
    // UYARI / VARSAYIM ŞERİDİ — ucun GERÇEK şeması (ÖH Z5 / OH-B4-01)
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (2026-08-27, app.test_client, POST /api/injector-design):
    // uç `design.warnings` ve `design.assumptions` yayımlıyor ve bunlar
    // {code, params, severity} KAYITLARIDIR (injector_design.py::_w;
    // severity ∈ {critical, warning, info}). Panel ise `dz.warnings_tr` /
    // `dz.assumptions_tr` okuyordu; bu iki adın ÜRETİCİSİ depoda YOK
    // (bekçisi: test_wave4b_contract::test_enjektor_borcunun_dayanagi_
    // olculdu). Yani şerit HER koşumda boştu. Ölçülen örnekler:
    //     hibrit / showerhead  -> warnings 0, assumptions 4
    //     hibrit / N2O pintle  -> warnings 1  (warn.injector.
    //                             hydraulic_flip_risk_ox, severity
    //                             'warning'), assumptions 5
    // Kullanıcı hidrolik-flip riskini ve "yoğunluk/viskozite tablodan
    // varsayıldı" künyelerini HİÇ görmüyordu.
    //
    // METİN: mevcut uyarı kimlik mekanizması kullanılır — kod kataloğu +
    // `TF(code, params)`. Kod sözlükte yoksa yedek metin KODUN KENDİSİ ve
    // parametreleridir (makine-yolu); uydurma cümle yazılmaz. Bu tur yeni
    // çeviri anahtarı AÇILMAZ.
    // ------------------------------------------------------------------

    //: severity -> rozet/kutu rengi. Bilinmeyen severity 'warn' sayılır
    //: (sessizce 'info'ya düşmek uyarıyı görünmez kılardı).
    const SEVERITY_KIND = {
        critical: 'err', error: 'err', warning: 'warn', warn: 'warn',
        info: 'info', notice: 'info',
    };

    function severityKind(rec) {
        const s = (rec && typeof rec === 'object') ? String(rec.severity || '') : '';
        return SEVERITY_KIND[s.toLowerCase()] || 'warn';
    }

    function severityLabel(rec) {
        const s = (rec && typeof rec === 'object') ? String(rec.severity || '') : '';
        return s ? s.toUpperCase() : '';
    }

    // Kayıt -> okunur metin. Üç biçim de desteklenir: düz metin (eski
    // sözleşme), {code, params, severity}, ve İÇ İÇE kayıt/kayıt listesi
    // (bir parametrenin değeri kendisi bir kayıt olabilir; I18N.tf sayı
    // olmayan parametreyi String(v) ile bastığı için çeviri ÖZYİNELEMELİ
    // olmalı — aksi hâlde "[object Object]" basılır).
    function warnText(w, depth) {
        depth = depth || 0;
        if (w === null || w === undefined) return '';
        if (typeof w === 'string') return w;
        if (Array.isArray(w)) {
            return w.map(function (x) { return warnText(x, depth + 1); })
                    .filter(function (s) { return s; })
                    .join(' · ');
        }
        if (typeof w !== 'object') return String(w);
        if (!w.code) return JSON.stringify(w);   // beklenmeyen biçim: görünür kıl
        if (depth > 4) return String(w.code);    // bozuk/döngüsel veri koruması
        const p = {};
        Object.keys(w.params || {}).forEach(function (k) {
            const v = w.params[k];
            p[k] = (v && typeof v === 'object') ? warnText(v, depth + 1) : v;
        });
        const params = Object.keys(p).map(function (k) {
            return k + '=' + String(p[k]);
        }).join(', ');
        return TF(w.code, p,
                  String(w.code) + (params ? ' [' + params + ']' : ''));
    }

    // Bir kayıt listesinin en ağır severity'si (kutu rengi buradan).
    function worstKind(records) {
        let kind = 'info';
        records.forEach(function (r) {
            const k = severityKind(r);
            if (k === 'err') kind = 'err';
            else if (k === 'warn' && kind !== 'err') kind = 'warn';
        });
        return kind;
    }

    function recordItemsHtml(records) {
        return records.map(function (r) {
            const kind = severityKind(r);
            const label = severityLabel(r);
            const tag = label
                ? '<span data-inj-severity="' + kind + '" style="font-family:'
                  + 'var(--hd-mono); font-size:0.68rem; letter-spacing:0.06em;'
                  + ' opacity:0.85;">[' + label + '] </span>'
                : '';
            return '<li>' + tag + warnText(r) + '</li>';
        }).join('');
    }

    // ------------------------------------------------------------------
    // Rozetler (spec bölüm D)
    // ------------------------------------------------------------------
    function badgesHtml(dz) {
        const st = dz.stability || {};
        const ox = dz.ox_circuit || {};
        const fu = dz.fuel_circuit;
        const at = dz.atomization || {};
        const mo = dz.momentum;
        let html = '';

        const dpPct = (st.dp_pc_ratio_ox != null) ? st.dp_pc_ratio_ox * 100 : null;
        html += badge(`dP/Pc ${fmt(dpPct, 0)}%`
            + (st.chug_ok ? '' : ' — ' + T('inj.chugRisk', 'CHUG RISK')),
            st.chug_ok ? 'ok' : 'err', st.chug_rule || '');

        const flowModel = ox.flow_model || 'SPI';
        html += badge(T('inj.modelBadge', 'MODEL') + ': ' + flowModel,
            (dz.fluid_ox === 'n2o' && flowModel !== 'NHNE') ? 'warn' : 'info',
            flowModel === 'NHNE'
                ? T('inj.nhneTip', 'Dyer NHNE two-phase model (AIAA 2007-5702)')
                : T('inj.spiTip', 'Single-phase SPI'));

        // --- ÖH D22 / OH-D17-09: "HÜKÜM VERİLMEDİ" ≠ "RİSK YOK" ---------
        // ÖLÇÜLDÜ (raw/OH/D22/arayuz/a1/once.json M1, taban b84b10a): uç
        // B4-05 hükmüyle `hydraulic_flip_risk`i ÜÇ DEĞERLİ yayımlıyor —
        // true / false / null. null = 'NOT DECIDED': çağıran orifis boyu
        // (plaka kalınlığı) ya da L/D vermediği için Nurick ölçütü modülün
        // 4,0 VARSAYILANINDAN hüküm üretemez (injector_design.py:1301-1319).
        // Panel bunu `||` ile okuduğu için null ile false AYNI HTML'i
        // veriyordu (`null_ile_false_ayni: true`, ikisinde de 2 rozet) ve
        // ucun `hydraulic_flip_risk_basis` künyesi HİÇBİR çıktıda geçmiyordu
        // (`basis_null_ciktisinda: false`). Yani "ölçemedik" ekranda
        // "güvenli"yle aynı görünüyordu — sessiz varsayılan.
        //
        // Kapı: üç durum üç ayrı görüntü. Uydurma yok — rozet yalnız uç
        // alanı GERÇEKTEN yayımladıysa doğar, künye yalnız uçtan gelir.
        // Devre adı yalnız iki devre varsa (sıvı) öne yazılır; hibritte tek
        // devre olduğu için eski etiket birebir korunur.
        const flipDevreler = fu ? [['OX', ox], ['FUEL', fu]] : [['', ox]];
        flipDevreler.forEach(function (d) {
            const c = d[1];
            if (!c || !('hydraulic_flip_risk' in c)) return;
            const onek = d[0] ? d[0] + ' ' : '';
            const kunye = c.hydraulic_flip_risk_basis || '';
            if (c.hydraulic_flip_risk === true) {
                html += badge(onek + T('inj.flipRisk', 'FLIP RISK'), 'err',
                    kunye || T('inj.flipTip',
                        'Hydraulic flip: cavitation-driven Cd collapse (Nurick 1976)'));
            } else if (c.hydraulic_flip_risk === null) {
                html += badge(onek + T('inj.flipUndecided', 'FLIP: NOT DECIDED'),
                    'warn', kunye || T('inj.flipUndecidedTip',
                        'The hydraulic-flip criterion reads L/D; no orifice '
                        + 'length or plate thickness was supplied, so no '
                        + 'verdict was published.'));
            }
        });

        if (mo && mo.momentum_ratio != null) {
            html += badge(`MR ${fmt(mo.momentum_ratio)} → `
                + T('inj.target', 'TARGET') + ' ' + fmt(mo.target),
                mo.ok ? 'ok' : 'warn', mo.rupe_factor != null ?
                (T('inj.rupeFactor', 'Rupe factor') + ': ' + fmt(mo.rupe_factor)) : '');
        } else if (mo && mo.tmr != null) {
            html += badge(`TMR ${fmt(mo.tmr)} → ` + T('inj.target', 'TARGET') + ' ' + fmt(mo.target),
                mo.ok ? 'ok' : 'warn');
        }

        if (at.smd_ox_um != null) {
            html += badge(`SMD ~${fmt(at.smd_ox_um, 0)} um (${at.correlation || '?'})`, 'info');
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Devre tablosu + tipe özel bloklar (spec bölüm D)
    // ------------------------------------------------------------------
    function circuitRows(name, c) {
        if (!c) return '';
        const man = c.manifold || {};
        return `<tr>
            <td>${name}</td>
            <td>${c.n_orifices != null ? c.n_orifices : '—'}</td>
            <td>${fmt(c.orifice_d_mm)}</td>
            <td>${fmt(c.total_area_mm2, 1)}</td>
            <td>${fmt(c.delta_p_bar, 1)}</td>
            <td>${fmt(c.velocity_m_s, 1)}</td>
            <td title="${c.cd_basis || ''}" style="cursor:help;">${fmt(c.cd)}</td>
            <td>${fmt(man.d_mm, 1)} mm · v/v=${fmt(man.v_ratio)}</td>
        </tr>`;
    }

    const TBL = 'width:100%; border-collapse:collapse; font-size:0.85rem; margin:8px 0;';
    const TD = 'padding:6px 8px; border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));';

    function specificBlock(dz) {
        const rows = [];
        if (dz.pintle_geometry) {
            const p = dz.pintle_geometry;
            rows.push([T('inj.pintleDia', 'Pintle diameter D_p'), fmt(p.d_pintle_mm) + ' mm'],
                      [T('inj.skipDistance', 'Skip distance'),
                       fmt(p.skip_distance_mm) + ' mm (L_s/D_p=' + fmt(p.ls_over_dp) + ')'],
                      [T('inj.blockageFactor', 'Blockage factor BF'), fmt(p.bf)],
                      [T('inj.annulusGap', 'Annulus gap'), fmt(p.annulus_gap_mm) + ' mm'],
                      [T('inj.radialHoles', 'Radial holes'),
                       TF('inj.radialHolesValue',
                          { n: p.n_radial_holes, d: fmt(p.radial_hole_d_mm) },
                          '{n} x dia {d} mm')]);
            if (p.single_fluid) {
                rows.push([T('inj.elementArrangement', 'Element arrangement'),
                           TF('inj.singleFluid',
                              // ÖH D25 / P11B2-12: `|| 0` yedeği çözücü
                              // oranı vermediğinde ekrana "radial flow
                              // share 0%" yazıyordu. fmt(null) '—' verir.
                              { pct: fmt(Number.isFinite(p.radial_flow_fraction)
                                         ? p.radial_flow_fraction * 100 : null, 0) },
                              'Single-fluid (oxidizer-centred hybrid pintle); '
                              + 'radial flow share {pct}%')]);
            }
        }
        if (dz.swirl_geometry) {
            const s = dz.swirl_geometry;
            rows.push([T('inj.swirlK', 'Swirl constant K'), fmt(s.K)],
                      [T('inj.airCore', 'Air core X'), fmt(s.X_air_core)],
                      [T('inj.cdSwirl', 'Cd (effective swirl)'), fmt(s.cd_swirl)],
                      [T('inj.filmThickness', 'Film thickness'), fmt(s.film_thickness_mm, 3) + ' mm'],
                      [T('inj.tangentialInlets', 'Tangential inlets'),
                       TF('inj.radialHolesValue',
                          { n: s.tangential_inlets, d: fmt(s.inlet_d_mm) },
                          '{n} x dia {d} mm')]);
        }
        if (dz.coaxial_geometry) {
            // V301/H2: tek akışkanlı koaksiyel eleman (devrenin kanonu).
            const c = dz.coaxial_geometry;
            rows.push([T('app.rep.coaxInnerJet', 'Inner Jet Diameter'),
                       fmt(c.inner_jet_diameter_mm) + ' mm'],
                      [T('app.rep.coaxAnnulusInner', 'Annulus Inner Diameter'),
                       fmt(c.annulus_inner_diameter_mm) + ' mm'],
                      [T('app.rep.coaxAnnulusOuter', 'Annulus Outer Diameter'),
                       fmt(c.annulus_outer_diameter_mm) + ' mm'],
                      [T('app.rep.coaxGap', 'Annulus Gap'), fmt(c.annulus_gap_mm, 3) + ' mm'],
                      [T('app.rep.coaxRecess', 'Recess (computed)'),
                       fmt(c.recess_length_mm) + ' mm'],
                      [T('app.rep.coaxInnerShare', 'Inner Jet Flow Share'),
                       fmt(Number.isFinite(c.inner_flow_fraction)
                           ? c.inner_flow_fraction * 100 : null, 1) + ' %']);
        }
        const imp = dz.pattern && dz.pattern.impingement;
        if (imp) {
            rows.push([T('inj.impingeAngle', 'Impingement half angle'),
                       fmt(imp.half_angle_deg, 1) + ' deg'],
                      [T('inj.freeJet', 'Free jet length'), fmt(imp.free_jet_length_mm, 1) + ' mm'],
                      [T('inj.elementSpacing', 'Element spacing'),
                       fmt(imp.element_spacing_mm, 1) + ' mm']);
        }
        const cone = dz.atomization && dz.atomization.spray_cone_half_angle_deg;
        if (cone != null) {
            rows.push([T('inj.sprayCone', 'Spray cone half angle'), fmt(cone, 1) + ' deg']);
        }
        if (!rows.length) return '';
        return `<h4 style="margin:12px 0 4px;">${T('inj.secGeometry',
            'Element-specific geometry')}</h4>
            <table style="${TBL}">` +
            rows.map(([k, v]) => `<tr><td style="${TD}"><strong>${k}</strong></td>
                <td style="${TD}">${v}</td></tr>`).join('') + '</table>';
    }

    function resultsHtml(dz) {
        const fu = dz.fuel_circuit;
        const at = dz.atomization || {};
        let html = '';

        // ÖH D30 / P11B5-21 + OH-D29-11 — İKİ KUSUR, TEK SATIR.
        // (1) Okunan anahtar `description_tr` idi: adı Türkçe içerik vaat
        //     ediyor, uç ise ona `description` ile BİT-AYNI İngilizce metni
        //     koyuyordu (ölçüldü: dört tipin dördünde `tr_ile_en_ayni`).
        //     Üretici (`injector_design.py`) yalan alanı D30'da söktü;
        //     panel dilden bağımsız `description`a geçti.
        // (2) Metin şablon içine HAM basılıyordu: uçtan gelen bir dize
        //     panelin HTML'ine doğrudan giriyordu. Artık `escText`ten
        //     geçer — içerik metindir, işaretleme değil.
        if (dz.pattern && dz.pattern.description) {
            html += `<p style="font-family:var(--hd-mono); font-size:0.85rem;
                color:var(--hd-ink-dim); margin:8px 0;">${escText(
                    // V301/DİL-2 (NK-35): üreticinin desen tanımı çeviri
                    // kanalından (serverText); tanınmazsa AYNEN.
                    (typeof window !== 'undefined' && window.I18N
                     && typeof window.I18N.serverText === 'function')
                        ? window.I18N.serverText(String(dz.pattern.description))
                        : dz.pattern.description)}</p>`;
        }

        html += `<table style="${TBL}">
            <thead><tr>
                <th style="${TD} text-align:left;">${T('inj.colCircuit', 'Circuit')}</th>
                <th style="${TD}">${T('inj.colOrifices', 'Orifices')}</th>
                <th style="${TD}">${T('inj.colDia', 'dia (mm)')}</th>
                <th style="${TD}">${T('inj.colArea', 'Total A (mm2)')}</th>
                <th style="${TD}">${T('inj.colDp', 'dP (bar)')}</th>
                <th style="${TD}">${T('inj.colV', 'v (m/s)')}</th>
                <th style="${TD}">C_d</th>
                <th style="${TD}">${T('inj.colManifold', 'Manifold')}</th>
            </tr></thead><tbody>` +
            circuitRows(T('common.oxidizer', 'Oxidizer'), dz.ox_circuit) +
            (fu ? circuitRows(T('common.fuel', 'Fuel'), fu) : '') +
            '</tbody></table>';
        // V301/L-C (SV-07): sıvı pintle'da tablonun delik sayısı/çapı devrenin
        // DELİNMEYEN eşdeğer düz orifis planıdır; delinen geometri aşağıdaki
        // pintle geometrisidir (ana tasarımın özet bloğuyla aynı tek kanon).
        if (dz.motor_type === 'liquid' && dz.pintle_geometry) {
            html += `<p style="font-size:0.8rem; color:var(--hd-ink-dim);">${
                (T('inj.pintleEquivPlanNote',
                    'Pintle: the orifice counts and diameters in this table are '
                    + 'the circuit\'s equivalent plain-orifice plan, used only to '
                    + 'size the flow areas; it is NOT drilled. The drilled '
                    + 'geometry is the pintle geometry below: radial fuel tip '
                    + 'holes and the oxidizer annulus around the post.'))}</p>`;
        }

        if (fu && at.smd_fuel_um != null) {
            html += `<p style="font-size:0.8rem; color:var(--hd-ink-dim);">${
                TF('inj.fuelSmd', { v: fmt(at.smd_fuel_um, 0) },
                   'Fuel circuit SMD: ~{v} um')}</p>`;
        }

        html += specificBlock(dz);

        // UYARILAR — ucun GERÇEK alanı `warnings` ({code,params,severity}).
        // Eski kod `dz.warnings_tr` okuyordu; o adın üreticisi yoktu ve
        // şerit hiç dolmuyordu (OH-B4-01). Kutu rengi listenin EN AĞIR
        // severity'sinden gelir; her satır kendi severity etiketini taşır
        // (renk tek başına taşıyıcı değildir).
        const warns = Array.isArray(dz.warnings) ? dz.warnings : [];
        if (warns.length) {
            const kind = worstKind(warns);
            const color = kind === 'err' ? 'var(--hd-red, #ff5d73)'
                : kind === 'info' ? 'var(--hd-cyan, #00e5ff)'
                    : 'var(--hd-orange, #ff8c33)';
            html += `<div data-inj-warnings="${warns.length}"
                style="border:1px solid ${color}; border-radius:8px;
                padding:10px 14px; margin:10px 0; color:${color};">
                <strong>${T('common.warnings', 'Warnings')}</strong>
                <ul style="margin:6px 0 0 18px;">`
                + recordItemsHtml(warns) + '</ul></div>';
        }

        // VARSAYIMLAR — `assumptions` (severity 'info' kayıtları).
        const assum = Array.isArray(dz.assumptions) ? dz.assumptions : [];
        if (assum.length) {
            html += `<details data-inj-assumptions="${assum.length}"
                style="margin:8px 0;"><summary style="cursor:pointer;
                color:var(--hd-ink-dim);">${T('common.assumptions', 'Assumptions')} (${assum.length})</summary>
                <ul style="margin:6px 0 0 18px; color:var(--hd-ink-dim); font-size:0.85rem;">`
                + recordItemsHtml(assum) + '</ul></details>';
        }

        const refs = dz.references || [];
        if (refs.length) {
            html += `<p style="font-size:0.72rem; color:var(--hd-ink-dim); margin-top:8px;">
                ${T('common.references', 'References')}: ${refs.join(' · ')}</p>`;
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Payload (spec bölüm B.1) — provider değerleri YALNIZ boş alanları
    // doldurur, sonra TEK kaynak olarak formdan okunur (kullanıcı ne
    // gönderildiğini görür ve elle girdiği değer korunur)
    // ------------------------------------------------------------------
    // V301/E2 — hibrit panelin alanlarını değer sözlüğüne okur / yazar.
    // Boş alan null'dır (yüke girmez); sayı olmayan girdi de null'a düşmez,
    // olduğu gibi (NaN) kalır ki uç onu adıyla reddedebilsin — sessiz
    // yedek yok.
    function readHybridValues() {
        const v = { injector_type: document.getElementById('inj_type').value };
        HYBRID_VALUE_FIELDS.forEach(function (f) {
            const el = document.getElementById(f[0]);
            if (!el) return;
            const raw = String(el.value == null ? '' : el.value).trim();
            v[f[1]] = raw === '' ? null : parseFloat(raw);
        });
        const n2oEl = document.getElementById('inj_n2o');
        v.n2o = !!(n2oEl && n2oEl.checked);
        const inl = document.getElementById('inj_inlet');
        v.inlet_ox = inl ? inl.value : 'sharp';
        const holes = document.getElementById('inj_pin_holes');
        v.secondary_holes = holes ? holes.value : null;
        if (v.secondary_holes === 'none') {
            v.pintle_radial_hole_count = null;
            v.pintle_radial_hole_diameter = null;
            v.skip_distance = null;
        }
        if (v.secondary_holes !== 'tangential') v.pintle_tangential_angle = null;
        v.radial_fraction = num('inj_radial_fraction', null);
        v.bf_target = num('inj_bf', null);
        if (cfg._tc != null) v.T_c_K = cfg._tc;
        if (cfg._mw != null) v.mw_gas = cfg._mw;
        return v;
    }

    function writeHybridValues(v) {
        HYBRID_VALUE_FIELDS.forEach(function (f) {
            const el = document.getElementById(f[0]);
            if (!el) return;
            const x = v[f[1]];
            el.value = sayiMi(x) ? String(Number(x.toPrecision(12))) : '';
        });
        const n2oEl = document.getElementById('inj_n2o');
        if (n2oEl) n2oEl.checked = !!v.n2o;
        const holes = document.getElementById('inj_pin_holes');
        if (holes && v.secondary_holes) holes.value = v.secondary_holes;
        cfg._tc = sayiMi(v.T_c_K) ? v.T_c_K : null;
        cfg._mw = sayiMi(v.mw_gas) ? v.mw_gas : null;
    }

    function buildSpec() {
        if (cfg.motorType === 'hybrid') {
            // V301/E2: hibrit yük TEK işlevden (specFromValues) — ana
            // tasarımla eşleme ve düğüm bekçisi aynı kodu kullanır.
            return specFromValues(readHybridValues());
        }
        if (cfg.motorType === 'liquid') {
            // V301/L-C: sıvı yük de TEK işlevden (specFromValues ←
            // readLiquidValues) — ana tasarımla eşleme ve düğüm bekçisi aynı
            // kodu kullanır. Panelin kendi pintle kolları (BF, TMR hedefi)
            // devrenin varsayılanlarıyla (0,58 / 1,0) aynı doğar.
            const lv = readLiquidValues();
            if (lv.injector_type === 'pintle') {
                lv.bf_target = num('inj_bf', null);
                lv.tmr_target = num('inj_tmr', null);
            }
            if (lv.injector_type === 'swirl' || lv.injector_type === 'coax_swirl') {
                lv.theta_target_deg = num('inj_theta', null);
            }
            return specFromValues(lv);
        }
        return null;
    }

    async function run() {
        const status = document.getElementById('inj_status');
        const badges = document.getElementById('inj_badges');
        const results = document.getElementById('inj_results');
        const btn = document.getElementById('inj_run');
        const typeEl = document.getElementById('inj_type');
        btn.disabled = true;
        badges.innerHTML = '';
        results.style.display = 'none';
        status.textContent = T('inj.designing', 'DESIGNING INJECTOR…');
        try {
            const resp = await fetch('/api/injector-design', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(buildSpec()),
            });
            const data = await resp.json();
            if (!resp.ok || data.status !== 'success') {
                // V301/E2: uç 422 gövdesinin AÇIKLAMA cümlesi ve adlı
                // alanları gösterilir (reject_body.js tek çözücü); eskiden
                // yalnız makine kodu basılıyordu.
                throw new Error((window.HRMAReject && window.HRMAReject.metni)
                    ? window.HRMAReject.metni(data, resp.status)
                    : (data.error || `HTTP ${resp.status}`));
            }
            const dz = data.design || {};
            if (dz.status === 'error') throw new Error(dz.error || 'design error');
            lastDesign = dz;
            lastDesignType = typeEl ? typeEl.value : null;
            badges.innerHTML = badgesHtml(dz);
            results.innerHTML = resultsHtml(dz);
            results.style.display = 'block';
            // Hesap bitti: çizim ARTIK bu hesabın geometrisini gösterir
            // (delik sayısı, delik çapı, D_p, sprey açısı...).
            if (lastDesignType) {
                renderSchematic(lastDesignType, schematicGeometry(dz));
            }
            status.textContent = '';
        } catch (err) {
            status.textContent = TF('common.errorPrefix', { message: err.message },
                                    'ERROR: {message}');
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // ÇİZİM ARTIK HESABI GÖRÜYOR (2026-08-09)
    // ------------------------------------------------------------------
    // Şema çizimi ile panelin hesabı arasında hiç veri yolu yoktu: panel
    // 17 radyal delik hesaplayıp tabloya bastığında bile çizimde SABİT
    // 2 ok kalıyordu. Bu işlev /api/injector-design yanıtını çizimin
    // anladığı sözlüğe indirger. Bir alan yanıtta yoksa buraya da
    // KONULMAZ; çizim o künyeyi hiç basmaz (uydurma değer yok).
    function schematicGeometry(dz) {
        if (!dz) return null;
        const g = {};
        const put = (key, value) => {
            if (typeof value === 'number' && isFinite(value)) g[key] = value;
        };
        const p = dz.pintle_geometry;
        if (p) {
            put('n_radial_holes', p.n_radial_holes);
            put('radial_hole_d_mm', p.radial_hole_d_mm);
            put('d_pintle_mm', p.d_pintle_mm);
            put('annulus_gap_mm', p.annulus_gap_mm);
            put('skip_distance_mm', p.skip_distance_mm);
            put('bf', p.bf);
            put('radial_flow_fraction', p.radial_flow_fraction);
            // single_fluid YALNIZ hibrit ox-merkezli pintle'da gelir; sıvı
            // yakıt-merkezli düzende hiç yoktur (iki akışkan).
            if (p.single_fluid) g.single_fluid = true;
        }
        const s = dz.swirl_geometry;
        if (s) {
            put('tangential_inlets', s.tangential_inlets);
            put('inlet_d_mm', s.inlet_d_mm);
            put('film_thickness_mm', s.film_thickness_mm);
            put('K', s.K);
        }
        const ox = dz.ox_circuit;
        if (ox) {
            put('n_orifices', ox.n_orifices);
            put('orifice_d_mm', ox.orifice_d_mm);
        }
        // V301/H2: koaksiyelde çizimin "inner jet" künyesi iç jet çapıdır
        // (devrenin eşdeğer düz orifis çapı DEĞİL); anülüs boşluğu da.
        const cg = dz.coaxial_geometry;
        if (cg) {
            put('orifice_d_mm', cg.inner_jet_diameter_mm);
            put('annulus_gap_mm', cg.annulus_gap_mm);
        }
        const pat = dz.pattern || {};
        put('n_elements', pat.n_elements);
        if (pat.impingement) put('half_angle_deg', pat.impingement.half_angle_deg);
        if (dz.atomization) {
            put('spray_half_angle_deg', dz.atomization.spray_cone_half_angle_deg);
        }
        // Tek akışkan bilgisi coax/showerhead için de anlamlı: hibritte
        // yakıt devresi YOKTUR.
        if (!dz.fuel_circuit) g.single_fluid = true;
        return g;
    }

    function renderSchematic(type, geom) {
        const host = document.getElementById('inj_schematic');
        if (!host) return;
        if (window.InjectorSchematics) {
            // geom verilmezse son tasarımdan türetilir; o da yoksa çizim
            // sayısal künyesiz genel hâliyle basılır.
            const same = window.InjectorSchematics.resolve
                ? (window.InjectorSchematics.resolve(lastDesignType)
                   === window.InjectorSchematics.resolve(type))
                : (lastDesignType === type);
            const g = (geom !== undefined) ? geom
                : (lastDesignType && same ? schematicGeometry(lastDesign) : null);
            window.InjectorSchematics.render(type, host, g);
        } else {
            host.style.display = 'none';
        }
    }

    function syncTypeFields() {
        const type = document.getElementById('inj_type').value;
        const show = (id, on) => {
            const el = document.getElementById(id);
            if (el) el.style.display = on ? '' : 'none';
        };
        show('inj_tmr_group', type === 'pintle');
        show('inj_radial_fraction_group', type === 'pintle');
        show('inj_bf_group', type === 'pintle');
        show('inj_theta_group', type === 'swirl' || type === 'coax_swirl');
        // V301/E2: hibrit eleman alanları yalnız kendi tipinde görünür.
        const holesEl = document.getElementById('inj_pin_holes');
        const holeMode = holesEl ? holesEl.value : 'radial';
        document.querySelectorAll('#injectorPanel [data-inj-group]').forEach(function (el) {
            const grp = el.getAttribute('data-inj-group');
            let on = grp === type;
            if (grp === 'liq-elements') on = (type !== 'pintle');
            if (grp === 'pintle-tangential') on = (type === 'pintle' && holeMode === 'tangential');
            if (on && type === 'pintle' && holeMode === 'none'
                    && ['inj_pin_n', 'inj_pin_d', 'inj_pin_ls'].some(function (id) {
                        return !!el.querySelector('#' + id); })) {
                on = false;
            }
            el.style.display = on ? '' : 'none';
        });

        // TMR HEDEFİ SALT KARŞILAŞTIRMADIR (sıvı pintle).
        // ÖLÇÜLDÜ (2026-08-09, /api/injector-design): tmr_target 0,5 ->
        // achieved 0,4747; tmr_target 2,0 -> achieved 0,4747. Yani alanın
        // sonuca hiçbir etkisi yok, yalnız rozetteki "TARGET" sayısını
        // değiştiriyor. Sessizce bırakmak kullanıcıyı bu kolu çevirdiğinde
        // motorun değiştiğine inandırıyordu.
        const tmrNote = document.getElementById('inj_tmr_note');
        if (tmrNote) {
            tmrNote.textContent = (type === 'pintle'
                    && document.getElementById('inj_tmr'))
                ? T('inj.tmrEchoNote',
                    'This target does not change the geometry: for a '
                    + 'fuel-centred pintle the achieved TMR follows from the '
                    + 'mass flows and injection velocities. The value you '
                    + 'enter is only the band the achieved TMR is compared '
                    + 'against.')
                : '';
        }
        const tox = document.getElementById('inj_tox');
        const n2o = document.getElementById('inj_n2o');
        if (tox && n2o) tox.parentElement.style.display = n2o.checked ? '' : 'none';
        // V301/H2: koaksiyel artık devrede — panel onu da tasarlar (eski
        // "düğme kapanır, şema basılmaz" dalı söküldü).
        const runBtn = document.getElementById('inj_run');
        if (runBtn && !cfg._running) runBtn.disabled = false;

        // İki-fazlı N2O açıkken dP/Pc alanı kullanıcı girdisi DEĞİLDİR:
        // basınç düşümü tank sıcaklığından (doyma basıncı) türer.
        const dpEl = document.getElementById('inj_dp');
        const note = document.getElementById('inj_dp_note');
        const twoPhase = !!(n2o && n2o.checked);
        if (dpEl) {
            dpEl.disabled = twoPhase;
            dpEl.style.opacity = twoPhase ? '0.5' : '';
            if (dpEl.parentElement) {
                dpEl.parentElement.title = twoPhase
                    ? T('inj.dpDisabledTip',
                        'Disabled: dP is set by tank temperature via Dyer NHNE '
                        + 'when two-phase N2O is enabled.')
                    : help('inj_dp');
            }
        }
        if (note) {
            note.textContent = twoPhase
                ? T('inj.dpNote',
                    'dP is set by tank temperature via Dyer NHNE when two-phase '
                    + 'N2O is enabled. Change the tank temperature to change dP.')
                : '';
        }

        const host = document.getElementById('inj_schematic');
        if (host) host.style.display = '';
        renderSchematic(type);
    }

    // ------------------------------------------------------------------
    // V301/E2 — ana tasarımla eşleme
    // ------------------------------------------------------------------
    // Hesaptan ÖNCE: panel ana formun tip seçimini izler (çelişen şema
    // gösterilmez). Kullanıcı panel tipini sonradan elle değiştirebilir.
    function followMainType(mainType) {
        const sel = document.getElementById('inj_type');
        if (!sel) return;
        // V301/L-C: sıvıda eşleme motorun KENDİ tablosudur
        // (INJECTOR_TYPE_CIRCUIT_MODEL; liquid.html init'e verir).
        const hedef = (cfg.motorType === 'liquid')
            ? (cfg.circuitModel || {})[mainType] : MAIN_TO_PANEL[mainType];
        if (hedef && sel.value !== hedef) sel.value = hedef;
        const note = document.getElementById('inj_sync_note');
        if (note && !cfg._synced) note.textContent = '';
        syncTypeFields();
    }

    // Hesaptan SONRA: alanlar devrenin girdileriyle dolar ve tasarım bir
    // kez koşar. values null ise (devre çözümü yok) panel dokunulmaz ve
    // nedeni yazılır.
    function syncFromEngine(values, mainType) {
        const note = document.getElementById('inj_sync_note');
        if (!values) {
            cfg._synced = false;
            syncTypeFields();
            return false;
        }
        const sel = document.getElementById('inj_type');
        if (sel) sel.value = values.injector_type;
        if (cfg.motorType === 'liquid') writeLiquidValues(values);
        else writeHybridValues(values);
        cfg._synced = true;
        syncTypeFields();
        if (note) {
            note.textContent = T('inj.syncedFromEngine',
                'Filled from the injector circuit of the main design (this '
                + 'calculation): the numbers below are that circuit. Change any '
                + 'field to explore an alternative.');
        }
        run();
        return true;
    }

    function init(options) {
        cfg = options || {};
        cfg.motorType = cfg.motorType === 'hybrid' ? 'hybrid' : 'liquid';
        cfg._synced = false;
        const anchor = cfg.anchorId ? document.getElementById(cfg.anchorId) : null;
        const host = document.createElement('div');
        host.innerHTML = panelHtml(cfg.motorType);
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid')
                || document.querySelector('.container')
                || document.body).appendChild(panel);
        }
        document.getElementById('inj_run').addEventListener('click', run);
        document.getElementById('inj_type').addEventListener('change', syncTypeFields);
        const holesSel = document.getElementById('inj_pin_holes');
        if (holesSel) holesSel.addEventListener('change', syncTypeFields);
        const n2o = document.getElementById('inj_n2o');
        if (n2o) n2o.addEventListener('change', syncTypeFields);
        syncTypeFields();
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);
        // Dil değişince: sabit etiketler I18N.apply ile, sonuç bloğu saklanan
        // tasarımla yeniden basılır.
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                syncTypeFields();
                if (!lastDesign) return;
                const badges = document.getElementById('inj_badges');
                const results = document.getElementById('inj_results');
                if (badges) badges.innerHTML = badgesHtml(lastDesign);
                if (results && results.style.display !== 'none') {
                    results.innerHTML = resultsHtml(lastDesign);
                }
            });
        }
    }

    window.InjectorPanel = {
        init, run, renderSchematic,
        // V301/E2: ana tasarımla eşleme (advanced.html çağırır).
        followMainType, syncFromEngine,
        engineValuesFromResults, specFromValues,
        // V301/L-C: sıvı yol (düğüm bekçisi aynı işlevleri çağırır).
        _liquidValuesFromResults: liquidValuesFromResults,
        // Test amaçlı saf render (dry-run): B.2 şemalı design → HTML
        _renderHtml: function (dz) { return badgesHtml(dz) + resultsHtml(dz); },
        // Test amaçlı saf dönüşüm: /api/injector-design yanıtı → çizim
        // geometrisi (panel ile şema arasındaki veri yolu).
        _schematicGeometry: schematicGeometry,
        // Test amaçlı saf yük kurucu (DOM gerektirir; tarayıcı testinde).
        _buildSpec: buildSpec,
    };
})();
