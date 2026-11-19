/* ====================================================================
   HRMA — Tank çalkantı modeli bölümü (calkanti_panel.js) · 3.0.7 K5
   --------------------------------------------------------------------
   V307/ÇALKANTI-ARAYÜZ (KARTLAR K5; CALKANTI_6DOF_TASARIM §A.3–A.6,
   TANK_GEOMETRI_TASARIM §0–§B). Analiz Güvertesi → Besleme Sistemi →
   Çalkantı sekmesinin altına takılır (sıvı: iki tank, hibrit: N₂O tankı;
   güverte motor sayfalarının sonuç bölümündedir). Katı motorda sekme yok;
   Besleme bölümünün başına tek satır: "Katı motorda sıvı itici yoktur;
   çalkantı uygulanmaz."

   Bu dosya SAYI ÜRETMEZ: her sayı /api/slosh-analysis (tank_modeli) ve
   /api/slosh-analysis/tank-geometry yanıtlarından gelir. Grafikler yalnız
   o yanıtın dizileriyle çizilir; dizi yoksa grafik konmaz, yerine
   "hesaplanmadı" ve sebep yazılır (sahte veri / sahte animasyon yok).
   Sunucu kodları (sebep/beyan) sözlükten EN + TR metne çevrilir; ham kod
   ekrana basılmaz. Sayılar dile göre ondalık ayraçla (U.num).
   ==================================================================== */
(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    function U() { return window.AnalysisDock && window.AnalysisDock.ui; }
    function T(k, f) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(k, f) : f;
    }
    function TF(k, p, f) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(k, p, f);
        return String(f || k).replace(/\{(\w+)\}/g, function (w, n) {
            return (p && n in p) ? String(p[n]) : w;
        });
    }
    function esc(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function sayi(x) { return typeof x === 'number' && Number.isFinite(x); }
    // V307/KIRMIZI-B — Plotly çizgi rengi TEMA TOKENİNDEN. Plotly CSS
    // değişkeni çözmez (renk dizesini kendi ayrıştırıcısıyla okur), bu yüzden
    // `var(--hd-X, #hex)` yazımı burada çözülür: token kökün hesaplanmış
    // stilinden okunur; okunamazsa (tema yüklenmemiş, node düzeneği) `var()`
    // içindeki yedek kullanılır — yedek tokenin değeriyle AYNI
    // (test_d20_electron_a1 yedek bekçisi). Renk değeri değişmez.
    function tokenRengi(css) {
        const m = /^var\(\s*(--[a-z0-9-]+)\s*,\s*(#[0-9a-fA-F]{6})\s*\)$/.exec(css);
        if (!m) return css;
        try {
            const v = window.getComputedStyle(document.documentElement)
                .getPropertyValue(m[1]).trim();
            if (/^#[0-9a-fA-F]{6}$/.test(v)) return v;
        } catch (e) { /* tema okunamadı: yedek */ }
        return m[2];
    }
    // Sayı yoksa EM TİRE; varsa dile göre ayraçla (TR virgül). Sayı DEĞİŞMEZ.
    function n(x, d) {
        if (!sayi(x)) return '—';
        const u = U();
        return u ? u.num(x, d) : x.toFixed(d);
    }
    // Anlamlı basamakla (çok küçük/büyük değerler için).
    function ns(x, basamak) {
        if (!sayi(x)) return '—';
        const v = Number(x.toPrecision(basamak || 4));
        const u = U();
        return u ? u.num(v) : String(v);
    }
    function yardim(key, text) {
        return (window.HRMAHelp && typeof window.HRMAHelp.html === 'function')
            ? window.HRMAHelp.html(key, T(key, text)) : '';
    }

    const UC = '/api/slosh-analysis';
    const UC_YUKLE = '/api/slosh-analysis/tank-geometry';
    const UC_AKTAR = '/api/slosh-analysis/export';

    // ------------------------------------------------------------------
    // Kod → sözlük anahtarı (LİTERAL; ölü-çeviri bekçisi anahtarları
    // kaynakta arar). Kapsam: K4 (slosh_motor_baglanti.KODLAR), sözleşme
    // (slosh_tablo.SEBEP_KODLARI), K5 (calkanti_arayuz.K5_KODLARI), K2
    // (six_dof_slosh.K2_KODLARI). Bekçi: tests/test_calkanti_arayuz.py
    // her Python kodunun burada olduğunu denetler.
    // ------------------------------------------------------------------
    const KOD = {
        TANK_YOK: 'panel.calkanti.kod.TANK_YOK',
        TANK_GEOMETRISI_YAYIMLANMADI: 'panel.calkanti.kod.TANK_GEOMETRISI_YAYIMLANMADI',
        TANK_GEOMETRISI_DIK_SILINDIR_DEGIL: 'panel.calkanti.kod.TANK_GEOMETRISI_DIK_SILINDIR_DEGIL',
        YOGUNLUK_YAYIMLANMADI: 'panel.calkanti.kod.YOGUNLUK_YAYIMLANMADI',
        YUKLENEN_KUTLE_YAYIMLANMADI: 'panel.calkanti.kod.YUKLENEN_KUTLE_YAYIMLANMADI',
        TUKETIM_YAYIMLANMADI: 'panel.calkanti.kod.TUKETIM_YAYIMLANMADI',
        DEBI_BUTCESI_TUTARSIZ: 'panel.calkanti.kod.DEBI_BUTCESI_TUTARSIZ',
        TUKETIM_SERISI_TUTARSIZ: 'panel.calkanti.kod.TUKETIM_SERISI_TUTARSIZ',
        UCUS_KUTLESIYLE_TUTARSIZ: 'panel.calkanti.kod.UCUS_KUTLESIYLE_TUTARSIZ',
        TANK_HACMI_YETERSIZ: 'panel.calkanti.kod.TANK_HACMI_YETERSIZ',
        TANK_GEOMETRISI_RET: 'panel.calkanti.kod.TANK_GEOMETRISI_RET',
        TANK_ISTASYONU_VERILMEDI: 'panel.calkanti.kod.TANK_ISTASYONU_VERILMEDI',
        MOTOR_BOYU_YAYIMLANMADI: 'panel.calkanti.kod.MOTOR_BOYU_YAYIMLANMADI',
        TANK_ARAC_DISI: 'panel.calkanti.kod.TANK_ARAC_DISI',
        TANK_BURUN_ICINDE: 'panel.calkanti.kod.TANK_BURUN_ICINDE',
        TANK_GOVDEDEN_GENIS: 'panel.calkanti.kod.TANK_GOVDEDEN_GENIS',
        TANKLAR_CAKISIYOR: 'panel.calkanti.kod.TANKLAR_CAKISIYOR',
        TUKETIM_SABIT_DEBI: 'panel.calkanti.kod.TUKETIM_SABIT_DEBI',
        TUKETIM_BOSALMA_COZUMU: 'panel.calkanti.kod.TUKETIM_BOSALMA_COZUMU',
        YOGUNLUK_SABIT: 'panel.calkanti.kod.YOGUNLUK_SABIT',
        YOGUNLUK_BOSALMA_COZUMU: 'panel.calkanti.kod.YOGUNLUK_BOSALMA_COZUMU',
        YOGUNLUK_SERISI_TUTARSIZ: 'panel.calkanti.kod.YOGUNLUK_SERISI_TUTARSIZ',
        BAFL_SONUMU_UYGULANMADI: 'panel.calkanti.kod.BAFL_SONUMU_UYGULANMADI',
        TANK_ISTASYONU_ARDISIK_DIZILIM: 'panel.calkanti.kod.TANK_ISTASYONU_ARDISIK_DIZILIM',
        TANK_ISTASYONU_SIVI_KM_DONUSUMU: 'panel.calkanti.kod.TANK_ISTASYONU_SIVI_KM_DONUSUMU',
        BOND_DUSUK_RET: 'panel.calkanti.kod.BOND_DUSUK_RET',
        BOND_BEYAN: 'panel.calkanti.kod.BOND_BEYAN',
        BOND_HESAPLANAMADI: 'panel.calkanti.kod.BOND_HESAPLANAMADI',
        IZGARA_DISI: 'panel.calkanti.kod.IZGARA_DISI',
        KUBBE_BOLGESI_SILINDIR_FORMULU_YOK: 'panel.calkanti.kod.KUBBE_BOLGESI_SILINDIR_FORMULU_YOK',
        TANK_BASLARI_MODELLENMEDI: 'panel.calkanti.kod.TANK_BASLARI_MODELLENMEDI',
        EKSENEL_SIMETRIK_DEGIL: 'panel.calkanti.kod.EKSENEL_SIMETRIK_DEGIL',
        YUZEY_KAPALI_DEGIL: 'panel.calkanti.kod.YUZEY_KAPALI_DEGIL',
        BAFL_GECERLILIK_DISI: 'panel.calkanti.kod.BAFL_GECERLILIK_DISI',
        GENLIK_DOGRUSAL_SINIR_DISI: 'panel.calkanti.kod.GENLIK_DOGRUSAL_SINIR_DISI',
        EKSIK_BOLGE: 'panel.calkanti.kod.EKSIK_BOLGE',
        PROFIL_TEK_DEGERLI_DEGIL: 'panel.calkanti.kod.PROFIL_TEK_DEGERLI_DEGIL',
        PROFIL_AG_HACIM_TUTARSIZ: 'panel.calkanti.kod.PROFIL_AG_HACIM_TUTARSIZ',
        AG_YAKINSAMA_ZAYIF: 'panel.calkanti.kod.AG_YAKINSAMA_ZAYIF',
        BIRIM_YOK: 'panel.calkanti.kod.BIRIM_YOK',
        STEP_MOZAIK_YOK: 'panel.calkanti.kod.STEP_MOZAIK_YOK',
        AG_URETILEMEDI: 'panel.calkanti.kod.AG_URETILEMEDI',
        GURULTU_ESIKLE_KIYASLANABILIR: 'panel.calkanti.kod.GURULTU_ESIKLE_KIYASLANABILIR',
        YUK_BAGINTISI_DIK_SILINDIR_ICIN: 'panel.calkanti.kod.YUK_BAGINTISI_DIK_SILINDIR_ICIN',
        BAFL_BAGINTISI_DIK_SILINDIR_ICIN: 'panel.calkanti.kod.BAFL_BAGINTISI_DIK_SILINDIR_ICIN',
        YUKLU_DOLULUK_IZGARA_DISI: 'panel.calkanti.kod.YUKLU_DOLULUK_IZGARA_DISI',
        ZAMAN_EKSENI_YOK: 'panel.calkanti.kod.ZAMAN_EKSENI_YOK',
        CEPER_SONUMU_TEK_GEFF_ISTER: 'panel.calkanti.kod.CEPER_SONUMU_TEK_GEFF_ISTER',
        TANK_KUTLESI_VERILMEDI: 'panel.calkanti.kod.TANK_KUTLESI_VERILMEDI',
        TANK_TUKETIMI_ITKIYLE_ORANTILI: 'panel.calkanti.kod.TANK_TUKETIMI_ITKIYLE_ORANTILI',
        TANK_KUTLE_SERISI_DISI: 'panel.calkanti.kod.TANK_KUTLE_SERISI_DISI',
        FX_POZITIF_DEGIL: 'panel.calkanti.kod.FX_POZITIF_DEGIL',
        YANMA_BITTI: 'panel.calkanti.kod.YANMA_BITTI',
        SATIR_RET: 'panel.calkanti.kod.SATIR_RET',
        RAY_STATIK_EGIM_SINIR_DISI: 'panel.calkanti.kod.RAY_STATIK_EGIM_SINIR_DISI',
        CEPER_SONUMU_HESAPLANAMADI: 'panel.calkanti.kod.CEPER_SONUMU_HESAPLANAMADI',
        I0_UYGULANMADI: 'panel.calkanti.kod.I0_UYGULANMADI',
        YARI_DURAGAN_DEGIL: 'panel.calkanti.kod.YARI_DURAGAN_DEGIL',
        SONUM_TOPLANABILIRLIGI: 'panel.calkanti.kod.SONUM_TOPLANABILIRLIGI',
        // ÇALKANTI-KARARLILIK (hüküm sözleşmesi §1, §6, §7)
        TANK_YOGUNLUK_SERISI_DISI: 'panel.calkanti.kod.TANK_YOGUNLUK_SERISI_DISI',
        TANK_YOGUNLUGU_SERIDEN: 'panel.calkanti.kod.TANK_YOGUNLUGU_SERIDEN',
        TARAMA_KISMI_KAPSAM: 'panel.calkanti.kod.TARAMA_KISMI_KAPSAM',
        ZETA_MIN_DOGRULANAMADI: 'panel.calkanti.kod.ZETA_MIN_DOGRULANAMADI',
        DONMUS_MODELDE_YERCEKIMI_KINEMATIGI_YOK: 'panel.calkanti.kod.DONMUS_MODELDE_YERCEKIMI_KINEMATIGI_YOK',
        ZETA_MIN_UST_SINIR_USTU: 'panel.calkanti.kod.ZETA_MIN_UST_SINIR_USTU',
        GEOMETRI_SILINDIR_DEGIL: 'panel.calkanti.kod.GEOMETRI_SILINDIR_DEGIL',
        HEDEF_HALKA_DIZISIYLE_SAGLANAMIYOR: 'panel.calkanti.kod.HEDEF_HALKA_DIZISIYLE_SAGLANAMIYOR',
        SONUM_GEREKSINIMI_YOK: 'panel.calkanti.kod.SONUM_GEREKSINIMI_YOK',
    };
    function kodMetni(kod) {
        const k = KOD[kod];
        return k ? T(k, kod) : T('panel.calkanti.kodTaninmadi',
            'A reason code this screen does not know was returned; the result is not shown as valid.');
    }

    // İçe aktarıcının (tank_geometry_import) ret/beyan metin anahtarı →
    // sözlük anahtarı. Parametreler ucun ``mesaj_parametreleri``nden.
    const GEO = {
        'tank_geometry.boyut_siniri.dosya_boyutu': 'panel.calkanti.geo.boyut_siniri.dosya_boyutu',
        'tank_geometry.boyut_siniri.nokta_siniri': 'panel.calkanti.geo.boyut_siniri.nokta_siniri',
        'tank_geometry.boyut_siniri.ucgen_siniri': 'panel.calkanti.geo.boyut_siniri.ucgen_siniri',
        'tank_geometry.boyut_siniri.profil_nokta_siniri': 'panel.calkanti.geo.boyut_siniri.profil_nokta_siniri',
        'tank_geometry.bicim_hatasi.bicim_desteklenmiyor': 'panel.calkanti.geo.bicim_hatasi.bicim_desteklenmiyor',
        'tank_geometry.bicim_hatasi.bos_dosya': 'panel.calkanti.geo.bicim_hatasi.bos_dosya',
        'tank_geometry.bicim_hatasi.metin_degil': 'panel.calkanti.geo.bicim_hatasi.metin_degil',
        'tank_geometry.bicim_hatasi.csv_baslik': 'panel.calkanti.geo.bicim_hatasi.csv_baslik',
        'tank_geometry.bicim_hatasi.sutun_sayisi': 'panel.calkanti.geo.bicim_hatasi.sutun_sayisi',
        'tank_geometry.bicim_hatasi.sayi_degil': 'panel.calkanti.geo.bicim_hatasi.sayi_degil',
        'tank_geometry.bicim_hatasi.ply_baslik': 'panel.calkanti.geo.bicim_hatasi.ply_baslik',
        'tank_geometry.bicim_hatasi.ply_buyuk_endian': 'panel.calkanti.geo.bicim_hatasi.ply_buyuk_endian',
        'tank_geometry.bicim_hatasi.ply_yuz_kose': 'panel.calkanti.geo.bicim_hatasi.ply_yuz_kose',
        'tank_geometry.bicim_hatasi.yuz_indeksi_gecersiz': 'panel.calkanti.geo.bicim_hatasi.yuz_indeksi_gecersiz',
        'tank_geometry.bicim_hatasi.ikili_boyut_tutarsiz': 'panel.calkanti.geo.bicim_hatasi.ikili_boyut_tutarsiz',
        'tank_geometry.bicim_hatasi.stl_ascii_yapi': 'panel.calkanti.geo.bicim_hatasi.stl_ascii_yapi',
        'tank_geometry.bicim_hatasi.step_baslik': 'panel.calkanti.geo.bicim_hatasi.step_baslik',
        'tank_geometry.bicim_hatasi.step_okunamadi': 'panel.calkanti.geo.bicim_hatasi.step_okunamadi',
        'tank_geometry.bicim_hatasi.step_govde_sayisi': 'panel.calkanti.geo.bicim_hatasi.step_govde_sayisi',
        'tank_geometry.bicim_hatasi.step_ucgen_yok': 'panel.calkanti.geo.bicim_hatasi.step_ucgen_yok',
        'tank_geometry.bicim_hatasi.ayristirici_hatasi': 'panel.calkanti.geo.bicim_hatasi.ayristirici_hatasi',
        'tank_geometry.deger_gecersiz.sonlu_olmayan': 'panel.calkanti.geo.deger_gecersiz.sonlu_olmayan',
        'tank_geometry.deger_gecersiz.bos_satir': 'panel.calkanti.geo.deger_gecersiz.bos_satir',
        'tank_geometry.deger_gecersiz.nokta_az': 'panel.calkanti.geo.deger_gecersiz.nokta_az',
        'tank_geometry.deger_gecersiz.ust_yon_gecersiz': 'panel.calkanti.geo.deger_gecersiz.ust_yon_gecersiz',
        'tank_geometry.deger_gecersiz.ust_yon_eksene_dik': 'panel.calkanti.geo.deger_gecersiz.ust_yon_eksene_dik',
        'tank_geometry.deger_gecersiz.eksen_gecersiz': 'panel.calkanti.geo.deger_gecersiz.eksen_gecersiz',
        'tank_geometry.deger_gecersiz.sigma_gecersiz': 'panel.calkanti.geo.deger_gecersiz.sigma_gecersiz',
        'tank_geometry.deger_gecersiz.profil_az_nokta': 'panel.calkanti.geo.deger_gecersiz.profil_az_nokta',
        'tank_geometry.deger_gecersiz.negatif_yaricap': 'panel.calkanti.geo.deger_gecersiz.negatif_yaricap',
        'tank_geometry.deger_gecersiz.boyut_sifir': 'panel.calkanti.geo.deger_gecersiz.boyut_sifir',
        'tank_geometry.tur_hatasi.profil_sayi_degil': 'panel.calkanti.geo.tur_hatasi.profil_sayi_degil',
        'tank_geometry.tur_hatasi.profil_bicimi': 'panel.calkanti.geo.tur_hatasi.profil_bicimi',
        'tank_geometry.alan_eksik.ust_yon_yok': 'panel.calkanti.geo.alan_eksik.ust_yon_yok',
        'tank_geometry.birim_yok.yok': 'panel.calkanti.geo.birim_yok.yok',
        'tank_geometry.birim_yok.desteklenmiyor': 'panel.calkanti.geo.birim_yok.desteklenmiyor',
        'tank_geometry.birim_yok.celiskili': 'panel.calkanti.geo.birim_yok.celiskili',
        'tank_geometry.birim_yok.step_basliginda_yok': 'panel.calkanti.geo.birim_yok.step_basliginda_yok',
        'tank_geometry.step_mozaik_yok.mozaikleyici_yok': 'panel.calkanti.geo.step_mozaik_yok.mozaikleyici_yok',
        'tank_geometry.yuzey_kapali_degil.dejenere_ucgen': 'panel.calkanti.geo.yuzey_kapali_degil.dejenere_ucgen',
        'tank_geometry.yuzey_kapali_degil.acik_kenar': 'panel.calkanti.geo.yuzey_kapali_degil.acik_kenar',
        'tank_geometry.yuzey_kapali_degil.manifold_degil': 'panel.calkanti.geo.yuzey_kapali_degil.manifold_degil',
        'tank_geometry.yuzey_kapali_degil.yonelim_tutarsiz': 'panel.calkanti.geo.yuzey_kapali_degil.yonelim_tutarsiz',
        'tank_geometry.yuzey_kapali_degil.euler': 'panel.calkanti.geo.yuzey_kapali_degil.euler',
        'tank_geometry.yuzey_kapali_degil.ters_yonelim': 'panel.calkanti.geo.yuzey_kapali_degil.ters_yonelim',
        'tank_geometry.yuzey_kapali_degil.bas_kapanmiyor': 'panel.calkanti.geo.yuzey_kapali_degil.bas_kapanmiyor',
        'tank_geometry.eksik_bolge.kapsama': 'panel.calkanti.geo.eksik_bolge.kapsama',
        'tank_geometry.profil_tek_degerli_degil.iki_yuzey': 'panel.calkanti.geo.profil_tek_degerli_degil.iki_yuzey',
        'tank_geometry.profil_tek_degerli_degil.z_monoton_degil': 'panel.calkanti.geo.profil_tek_degerli_degil.z_monoton_degil',
        'tank_geometry.profil_tek_degerli_degil.ic_dugum_eksende': 'panel.calkanti.geo.profil_tek_degerli_degil.ic_dugum_eksende',
        'tank_geometry.profil_tek_degerli_degil.kendini_kesiyor': 'panel.calkanti.geo.profil_tek_degerli_degil.kendini_kesiyor',
        'tank_geometry.eksenel_simetrik_degil.esik': 'panel.calkanti.geo.eksenel_simetrik_degil.esik',
        'tank_geometry.profil_ag_hacim_tutarsiz.hacim': 'panel.calkanti.geo.profil_ag_hacim_tutarsiz.hacim',
        'tank_geometry.beyan.gurultu_esikle_kiyaslanabilir': 'panel.calkanti.geo.beyan.gurultu_esikle_kiyaslanabilir',
    };
    const UC_ADI = { alt: 'panel.calkanti.geo.uc.alt', ust: 'panel.calkanti.geo.uc.ust' };
    function geoParam(p) {
        const out = {};
        Object.keys(p || {}).forEach(function (k) {
            const v = p[k];
            if (k === 'uc' && UC_ADI[v]) {
                out[k] = T(UC_ADI[v], v);
            } else if (sayi(v)) {
                out[k] = Number.isInteger(v) ? String(v) : ns(v, 4);
            } else if (Array.isArray(v)) {
                out[k] = v.map(function (x) { return Array.isArray(x) ? x.join('–') : x; }).join(', ');
            } else {
                out[k] = String(v == null ? '' : v);
            }
        });
        return out;
    }
    function geoMetni(anahtar, params, yedek) {
        const k = GEO[anahtar];
        if (!k) return yedek || T('panel.calkanti.kodTaninmadi',
            'A reason code this screen does not know was returned; the result is not shown as valid.');
        return TF(k, geoParam(params), yedek || '');
    }

    const TANK_ADI = {
        oksitleyici: ['panel.calkanti.tank.oksitleyici', 'Oxidizer tank'],
        yakit: ['panel.calkanti.tank.yakit', 'Fuel tank'],
        n2o: ['panel.calkanti.tank.n2o', 'N₂O tank'],
    };
    function tankAdi(tid) {
        const a = TANK_ADI[tid];
        return a ? T(a[0], a[1]) : String(tid);
    }
    const DURUM = {
        GECERLI: ['panel.calkanti.durum.GECERLI', 'VALID'],
        BEYANLI: ['panel.calkanti.durum.BEYANLI', 'DECLARED'],
        RET: ['panel.calkanti.durum.RET', 'REJECTED'],
    };
    function durumMetni(d) {
        const a = DURUM[d];
        return a ? T(a[0], a[1]) : String(d);
    }
    const YOL = {
        silindir_kapali_bicim: ['panel.calkanti.yol.silindir_kapali_bicim',
            'closed form, upright flat-bottom cylinder (Dodge 2000 Eq. (1.40), Table 3.2; NASA SP-8009 Table I)'],
        profil_kapali_bicim_h_es: ['panel.calkanti.yol.profil_kapali_bicim_h_es',
            'cylinder formula with the equivalent depth h_eq = V/(πR²) on a headed tank (declared; the numerical method is recommended)'],
        profil_sayisal_se: ['panel.calkanti.yol.profil_sayisal_se',
            'axisymmetric finite-element solution of the tank profile'],
        geometri_ret: ['panel.calkanti.yol.geometri_ret', 'geometry rejected; no table'],
    };
    function yolMetni(y) {
        const a = YOL[y];
        return a ? T(a[0], a[1]) : '—';
    }

    // ------------------------------------------------------------------
    // Form (her girdinin yanında "?" ipucu, EN + TR)
    // ------------------------------------------------------------------
    const YONTEMLER = [
        ['otomatik', 'Automatic', 'panel.calkanti.yontem.otomatik'],
        ['kapali_bicim', 'Closed form (cylinder formula)', 'panel.calkanti.yontem.kapali_bicim'],
        ['sayisal', 'Numerical (finite element)', 'panel.calkanti.yontem.sayisal'],
    ];
    const BIRIMLER = [
        ['', 'Choose…', 'panel.calkanti.birimSec'],
        ['m', 'm', ''], ['mm', 'mm', ''], ['in', 'in', ''],
    ];

    function etiket(key, text, forId) {
        return '<label for="' + forId + '" data-i18n="' + key + '">' + esc(T(key, text)) + '</label>';
    }
    function alanBasi(key, text, helpKey, helpText, forId) {
        return '<div class="ad-field-head">' + etiket(key, text, forId) + yardim(helpKey, helpText) + '</div>';
    }
    function secenekler(liste, secili) {
        return liste.map(function (o) {
            return '<option value="' + o[0] + '"' + (o[0] === secili ? ' selected' : '')
                + (o[2] ? ' data-i18n="' + o[2] + '"' : '') + '>'
                + esc(o[2] ? T(o[2], o[1]) : o[1]) + '</option>';
        }).join('');
    }

    function formHtml(mt) {
        const tanklar = mt === 'liquid' ? ['oksitleyici', 'yakit'] : ['n2o'];
        const tankSec = tanklar.map(function (t) {
            const a = TANK_ADI[t];
            return '<option value="' + t + '" data-i18n="' + a[0] + '">' + esc(T(a[0], a[1])) + '</option>';
        }).join('');
        const grid = 'display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:10px; margin:6px 0;';
        return ''
            + '<div style="' + grid + '">'
            + '<div class="form-group">' + alanBasi('panel.calkanti.fGeffMin', 'Effective axial acceleration, lower (m/s²)',
                'panel.calkanti.help.g_eff_min',
                'Effective axial acceleration that restores the liquid surface, m/s² (finite, > 0). The slosh frequency scales as √g_eff; the slosh mass ratio, pendulum length and positions do not depend on it. Blank: standard gravity g0 = 9.80665 m/s² (1 g) is used and stated in the result. With an upper value as well, the range is mapped with 11 equally spaced values.',
                'clk_geff_min')
            + '<input type="number" id="clk_geff_min" step="0.1" min="0" value=""></div>'
            + '<div class="form-group">' + alanBasi('panel.calkanti.fGeffMax', 'Effective axial acceleration, upper (m/s²)',
                'panel.calkanti.help.g_eff_max',
                'Upper end of an effective axial acceleration range, m/s² (finite, greater than the lower value). Blank: a single value is used. With a range the frequency map has 11 equally spaced acceleration values, the loads are given at the upper value (they scale linearly with the acceleration), and the time table carries κ1 instead of ω1 (the vehicle team computes ω1 = √(κ1·g_eff) at its own acceleration).',
                'clk_geff_max')
            + '<input type="number" id="clk_geff_max" step="0.1" min="0" value=""></div>'
            + '<div class="form-group">' + alanBasi('panel.calkanti.fYontem', 'Model method',
                'panel.calkanti.help.yontem',
                'How the equivalent-model table is built. Automatic: an upright flat-bottom cylinder uses the closed form (Dodge 2000 Eq. (1.40), Table 3.2); any other axisymmetric tank uses the axisymmetric finite-element solution. Closed form on a headed tank applies the cylinder formula with the equivalent depth h_eq = V/(πR²) and declares it; rows with the free surface in a head are rejected. Numerical always uses the finite-element solution. Blank: Automatic.',
                'clk_yontem')
            + '<select id="clk_yontem">' + secenekler(YONTEMLER, 'otomatik') + '</select></div>'
            + '<div class="form-group" style="align-self:end;"><button class="btn" type="button" id="clk_hesapla" data-i18n="panel.calkanti.btnRun">'
            + esc(T('panel.calkanti.btnRun', 'Compute tank model')) + '</button></div>'
            + '</div>'
            + '<details style="margin:6px 0;"><summary style="cursor:pointer; font-size:0.82rem;" data-i18n="panel.calkanti.secGeo">'
            + esc(T('panel.calkanti.secGeo', 'Tank geometry from a file (optional)')) + '</summary>'
            + '<div style="' + grid + '">'
            + '<div class="form-group">' + alanBasi('panel.calkanti.fGeoTank', 'Tank to replace',
                'panel.calkanti.help.geo_tank',
                'Which of this motor\'s tanks the uploaded inner geometry replaces. Without an upload the motor\'s own flat-capped upright cylinder (diameter and length from the motor design) is used.',
                'clk_geo_tank')
            + '<select id="clk_geo_tank">' + tankSec + '</select></div>'
            + '<div class="form-group">' + alanBasi('panel.calkanti.fGeoFile', 'Tank inner geometry file',
                'panel.calkanti.help.geo_file',
                'Inner surface of the tank: point cloud CSV (header x,y,z), XYZ, PLY or STL mesh, STEP solid (the tank interior volume as one solid), or an (r,z) profile CSV from the bottom pole to the top pole. Size limit 32 MB per upload (STEP 16 MB). A tank that is not axisymmetric is rejected by name and not solved in this version; no approximate result is given. Blank: the motor\'s own cylinder is used.',
                'clk_geo_file')
            + '<input type="file" id="clk_geo_file" accept=".csv,.xyz,.ply,.stl,.step,.stp"></div>'
            + '<div class="form-group">' + alanBasi('panel.calkanti.fGeoUnit', 'Length unit of the file',
                'panel.calkanti.help.geo_unit',
                'Length unit of the coordinates in the file: m, mm or in. Required; it is never guessed. If the unit line of the CSV or the STEP header declares a different unit, the file is rejected by name.',
                'clk_geo_unit')
            + '<select id="clk_geo_unit">' + secenekler(BIRIMLER, '') + '</select></div>'
            + '<div class="form-group">' + alanBasi('panel.calkanti.fGeoUp', 'Nose direction (x,y,z)',
                'panel.calkanti.help.geo_up',
                'Direction in the file\'s coordinates that points to the vehicle nose: three numbers "x,y,z", not all zero. Required for 3D files (point cloud, mesh, STEP): it decides which end of the tank faces the nose and must lie within 60° of the tank axis. Not used for an (r,z) profile. Blank with a 3D file: the file is rejected by name.',
                'clk_geo_up')
            + '<input type="text" id="clk_geo_up" placeholder="0,0,1" value=""></div>'
            + '<div class="form-group" style="align-self:end;"><button class="btn" type="button" id="clk_geo_yukle" data-i18n="panel.calkanti.btnUpload">'
            + esc(T('panel.calkanti.btnUpload', 'Upload geometry')) + '</button></div>'
            + '</div>'
            + '<div id="clk_geo_durum" style="font-size:0.8rem; margin:4px 0;"></div>'
            + '<div id="clk_geo_liste" style="font-size:0.8rem; margin:4px 0;"></div>'
            + '</details>';
    }

    // ------------------------------------------------------------------
    // Durum
    // ------------------------------------------------------------------
    const durumlar = {
        kok: null,
        geometriler: {},      // tank_id -> {profil_rz_m, dosya_adi, sha256, sebep, geometri}
        sonIstek: null,       // son başarılı hesabın tank_modeli gövdesi
        sonVeri: null,        // son başarılı yanıtın tank_modeli bloğu
    };

    // Motor türü SAYFANIN YOLUNDAN (/liquid, /hybrid, /solid): 6-DOF paneli
    // güverteden ÖNCE kurulur (DOMContentLoaded sırası) ve o anda güverte
    // kendi varsayılanını döndürür; sayfa yolu tek ve kesin kaynaktır.
    // Yol tanınmazsa güvertenin yapılandırması.
    const SAYFA_TURU = { liquid: 'liquid', hybrid: 'hybrid', solid: 'solid' };
    function motorTuru() {
        const son = String((window.location && window.location.pathname) || '')
            .replace(/\/+$/, '').split('/').pop();
        if (SAYFA_TURU[son]) return SAYFA_TURU[son];
        return (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function')
            ? window.AnalysisDock.getMotorType() : null;
    }

    function sayiAlan(id) {
        const el = document.getElementById(id);
        if (!el || el.value === '') return null;
        const v = Number(String(el.value).replace(',', '.'));
        return Number.isFinite(v) ? v : NaN;
    }

    function istekGovdesi() {
        const mt = motorTuru();
        const govde = { motor_type: mt };
        if (mt !== 'solid') govde.motor_sonucu = window.currentResults || null;
        const lo = sayiAlan('clk_geff_min');
        const hi = sayiAlan('clk_geff_max');
        if (lo !== null && hi !== null) govde.g_eff_m_s2 = [lo, hi];
        else if (lo !== null) govde.g_eff_m_s2 = lo;
        else if (hi !== null) govde.g_eff_m_s2 = [null, hi];
        const y = document.getElementById('clk_yontem');
        if (y && y.value) govde.yontem = y.value;
        const g = {};
        Object.keys(durumlar.geometriler).forEach(function (tid) {
            const k = durumlar.geometriler[tid];
            g[tid] = { profil_rz_m: k.profil_rz_m, dosya_adi: k.dosya_adi,
                       sha256: k.sha256, sebep: k.sebep };
        });
        if (Object.keys(g).length) govde.tank_geometrileri = g;
        return govde;
    }

    // Ret gövdesinin okunur cümlesi: içe aktarıcı metni → sebep kodu →
    // alan sınıfı → genel cümle. Sunucunun İngilizce cümlesi TR ekrana
    // basılmaz; ham kod gösterilmez.
    function retMetni(govde, kod) {
        const g = (govde && typeof govde === 'object') ? govde : {};
        if (g.mesaj_anahtari && GEO[g.mesaj_anahtari]) {
            return geoMetni(g.mesaj_anahtari, g.mesaj_parametreleri, g.message);
        }
        const alan = (g.invalid_fields && g.invalid_fields[0]) || {};
        const sebep = alan.reason || g.kod;
        const f = String(alan.field || g.alan || '');
        if (sebep && KOD[sebep]) return kodMetni(sebep);
        if (f.indexOf('g_eff') >= 0) {
            return T('panel.calkanti.retGeff',
                'The effective axial acceleration values are not usable: give one positive value, or a lower and an upper value with the upper one larger.');
        }
        if (sebep === 'MOTOR_SONUCU_OKUNAMADI' || sebep === 'MOTOR_SONUCU_HATA' || f.indexOf('motor_sonucu') >= 0) {
            return T('panel.calkanti.retMotor',
                'The motor result of this page could not be read; calculate the motor again.');
        }
        if (kod === 413 || sebep === 'BOYUT_SINIRI') {
            return T('panel.calkanti.retBoyut', 'The file is larger than the upload limit; nothing was read.');
        }
        return T('panel.calkanti.retGenel', 'The request was rejected; nothing was computed.');
    }

    // ------------------------------------------------------------------
    // Yükleme
    // ------------------------------------------------------------------
    async function geometriYukle() {
        const st = document.getElementById('clk_geo_durum');
        const dosya = document.getElementById('clk_geo_file');
        const birim = document.getElementById('clk_geo_unit');
        const ust = document.getElementById('clk_geo_up');
        const tank = document.getElementById('clk_geo_tank');
        if (!st || !dosya || !dosya.files || !dosya.files.length) {
            if (st) st.textContent = T('panel.calkanti.geoDosyaYok', 'Choose a file first.');
            return;
        }
        const fd = new FormData();
        fd.append('file', dosya.files[0]);
        fd.append('birim', birim ? birim.value : '');
        if (ust && ust.value.trim()) fd.append('ust_yon', ust.value.trim());
        st.textContent = T('panel.calkanti.geoOkunuyor', 'Reading the file…');
        try {
            const r = await fetch(UC_YUKLE, { method: 'POST', body: fd });
            let j = null;
            try { j = await r.json(); } catch (e) { j = null; }
            if (!r.ok || !j || j.status !== 'success') {
                st.textContent = TF('panel.calkanti.geoReddedildi', { reason: retMetni(j, r.status) },
                    'Geometry rejected: {reason}');
                return;
            }
            const g = j.geometri;
            const kn = g.kunye || {};
            durumlar.geometriler[tank.value] = {
                profil_rz_m: g.profil_rz_m, dosya_adi: kn.dosya_adi, sha256: kn.sha256,
                sebep: g.sebep || [], geometri: g.geometri || {}, beyanlar: g.beyanlar || [],
            };
            st.textContent = TF('panel.calkanti.geoKabul', {
                file: kn.dosya_adi || '—',
                R: ns(g.geometri && g.geometri.R_ref_m, 5),
                H: ns(g.geometri && g.geometri.H_ic_m, 5),
                V: ns(g.geometri && g.geometri.V_ic_m3, 5),
            }, 'Geometry accepted: {file} — R = {R} m, H = {H} m, V = {V} m³. Run the tank model to use it.');
            geometriListesi();
        } catch (e) {
            st.textContent = TF('panel.calkanti.geoReddedildi', { reason: String(e && e.message || e) },
                'Geometry rejected: {reason}');
        }
    }

    function geometriListesi() {
        const el = document.getElementById('clk_geo_liste');
        if (!el) return;
        const satir = Object.keys(durumlar.geometriler).map(function (tid) {
            const k = durumlar.geometriler[tid];
            const beyan = (k.beyanlar || []).map(function (b) {
                return geoMetni(b.mesaj_anahtari, b.mesaj_parametreleri, b.mesaj_en);
            }).join(' ');
            return '<div>' + esc(TF('panel.calkanti.geoKullanimda', { tank: tankAdi(tid), file: k.dosya_adi || '—' },
                    '{tank}: geometry from {file}'))
                + (beyan ? ' — ' + esc(beyan) : '')
                + ' <button type="button" class="btn" data-clk-kaldir="' + esc(tid) + '" style="padding:2px 8px; font-size:0.72rem;" data-i18n="panel.calkanti.btnRemoveGeo">'
                + esc(T('panel.calkanti.btnRemoveGeo', 'Remove')) + '</button></div>';
        }).join('');
        el.innerHTML = satir;
        el.querySelectorAll('[data-clk-kaldir]').forEach(function (b) {
            b.addEventListener('click', function () {
                delete durumlar.geometriler[b.getAttribute('data-clk-kaldir')];
                geometriListesi();
            });
        });
    }

    // ------------------------------------------------------------------
    // Hesap
    // ------------------------------------------------------------------
    async function hesapla() {
        const st = document.getElementById('clk_durum');
        const sonuc = document.getElementById('clk_sonuc');
        if (!st || !sonuc) return;
        const mt = motorTuru();
        if (mt !== 'solid' && !window.currentResults) {
            st.textContent = T('panel.calkanti.motorYok',
                'Calculate the motor first; the tank model uses this motor\'s tanks and propellant consumption.');
            return;
        }
        const govde = istekGovdesi();
        st.textContent = T('common.running', 'RUNNING…');
        try {
            const r = await fetch(UC, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ tank_modeli: govde }) });
            let j = null;
            try { j = await r.json(); } catch (e) { j = null; }
            if (!r.ok || !j || j.status !== 'success') {
                st.textContent = TF('common.errorPrefix', { message: retMetni(j, r.status) }, 'ERROR: {message}');
                return;
            }
            durumlar.sonIstek = govde;
            durumlar.sonVeri = j.tank_modeli;
            st.textContent = '';
            ciz();
        } catch (e) {
            st.textContent = TF('common.errorPrefix', { message: String(e && e.message || e) }, 'ERROR: {message}');
        }
    }

    async function indir(tid, bicim) {
        const st = document.getElementById('clk_durum');
        if (!durumlar.sonIstek) return;
        try {
            const r = await fetch(UC_AKTAR, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tank_modeli: durumlar.sonIstek, disa_aktarim: { tank_id: tid, bicim: bicim } }) });
            if (!r.ok) {
                let j = null;
                try { j = await r.json(); } catch (e) { j = null; }
                if (st) st.textContent = TF('common.errorPrefix', { message: retMetni(j, r.status) }, 'ERROR: {message}');
                return;
            }
            const cd = r.headers.get('Content-Disposition') || '';
            const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
            const ad = m ? decodeURIComponent(m[1]) : ('HRMA_calkanti_' + tid);
            const blob = await r.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = ad;
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
        } catch (e) {
            if (st) st.textContent = TF('common.errorPrefix', { message: String(e && e.message || e) }, 'ERROR: {message}');
        }
    }

    // ------------------------------------------------------------------
    // Çizim
    // ------------------------------------------------------------------
    function eksen(baslik) {
        return { title: { text: baslik, font: { size: 14 } }, tickfont: { size: 12 }, automargin: true };
    }
    function cizimDuzeni(baslik, x, y, ek) {
        const d = { title: { text: baslik, font: { size: 15 } }, xaxis: eksen(x), yaxis: eksen(y),
                    font: { size: 12 }, height: 400, margin: { t: 60, b: 120, l: 70, r: 70 },
                    legend: { orientation: 'h', y: -0.34, font: { size: 12 } } };
        return Object.assign(d, ek || {});
    }

    function kodListesi(baslik, kodlar, tur) {
        const u = U();
        const metinler = (kodlar || []).map(kodMetni);
        if (!metinler.length) return '';
        return u ? u.listBlock(esc(baslik), metinler, tur) : '';
    }

    function tankBolumu(t, i, veri) {
        const u = U();
        const kok = document.createElement('div');
        kok.style.cssText = 'border-top:1px solid var(--hd-line, rgba(0,229,255,0.14)); margin-top:12px; padding-top:6px;';
        const baslik = tankAdi(t.tank_id) + ' — ' + esc(t.sivi_adi || '');
        let html = u.sectionTitle(esc(baslik));
        const hesap = !!t.tablo;
        html += '<div style="font-size:0.82rem; margin:2px 0 6px;">'
            + esc(hesap ? T('panel.calkanti.tankHesaplandi', 'Equivalent-model table computed.')
                        : T('panel.calkanti.tankHesaplanmadi', 'Not computed; the reasons are listed below.'))
            + (t.tablo_yolu ? ' ' + esc(TF('panel.calkanti.yolSatiri', { yol: yolMetni(t.tablo_yolu) }, 'Method: {yol}.')) : '')
            + '</div>';
        // Sebepler (tank bağlanmadı / hesaplanmadı)
        html += kodListesi(T('panel.calkanti.sebepler', 'Why parts of the result are missing'), t.sebep, 'warn');
        if (t.geometri_girdisi && t.geometri_girdisi.mesaj_anahtari) {
            html += u.listBlock(esc(T('panel.calkanti.geoRetBaslik', 'Tank geometry rejected')),
                [geoMetni(t.geometri_girdisi.mesaj_anahtari, t.geometri_girdisi.mesaj_parametreleri,
                          t.geometri_girdisi.mesaj_en)], 'err');
        }
        // Kartlar
        const yuklu = (t.tablo && sayi(t.yuklu_doluluk)) ? yukluSatir(t) : null;
        const f1 = t.f1_hz_1g || {};
        const f1Ayni = sayi(f1.motor) && sayi(f1.tablo)
            && Math.abs(f1.motor - f1.tablo) <= 1e-9 * Math.max(Math.abs(f1.motor), Math.abs(f1.tablo));
        const geoDosya = !!t.geometri_dosyasi;
        html += '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:8px 0;">'
            + u.statCard(esc(T('panel.calkanti.cYuklenen', 'LOADED LIQUID')), n(t.yuklenen_sivi_kg, 3), 'kg', 'dim',
                esc(T('panel.calkanti.cYuklenenTip', 'Liquid mass the motor loads into this tank (motor result).')))
            + u.statCard(esc(T('panel.calkanti.cYogunluk', 'LIQUID DENSITY')), n(t.rho_kg_m3, 2), 'kg/m³', 'dim',
                esc(T('panel.calkanti.cYogunlukTip', 'Liquid density used for the fill fraction, from the motor result; held constant during the burn (declared).')))
            + u.statCard(esc(T('panel.calkanti.cDoluluk', 'LOADED FILL')), n(t.yuklu_doluluk, 4), '', 'dim',
                esc(T('panel.calkanti.cDolulukTip', 'Liquid volume / tank inner volume at ignition.')))
            + u.statCard(esc(T('panel.calkanti.cF1', 'f1 AT 1 g, LOADED')),
                (f1Ayni || !sayi(f1.motor) || geoDosya) ? n(f1.tablo, 4) : (n(f1.tablo, 4) + ' / ' + n(f1.motor, 4)), 'Hz', 'info',
                esc(T('panel.calkanti.cF1Tip', 'Fundamental slosh frequency at 1 g and the loaded fill, from the equivalent-model table; the same number as the tank slosh frequency of the motor card.')))
            + u.statCard(esc(T('panel.calkanti.cM1', 'SLOSH MASS m1, LOADED')),
                yuklu && sayi(yuklu.m1_oran) ? n(yuklu.m1_oran * t.yuklenen_sivi_kg, 3) : '—', 'kg', 'dim',
                esc(T('panel.calkanti.cM1Tip', 'Mass taking part in the first slosh mode at the loaded fill (m1/m from the table × loaded liquid).')))
            + u.statCard(esc(T('panel.calkanti.cL1', 'PENDULUM LENGTH L1, LOADED')),
                yuklu ? n(yuklu.L1_m, 4) : '—', 'm', 'dim',
                esc(T('panel.calkanti.cL1Tip', 'Equivalent pendulum length L1 = 1/κ1 at the loaded fill; independent of the effective axial acceleration.')))
            + '</div>';
        // Tek büyüklük, tek sayı: iki değer ayrışıyorsa fark ve NEDENİ yan yana.
        if (!f1Ayni && sayi(f1.motor) && sayi(f1.tablo)) {
            html += '<div style="font-size:0.8rem; margin:0 0 6px;">' + esc(geoDosya
                ? TF('panel.calkanti.f1GeoNot', { m: n(f1.motor, 4) },
                     'The motor card\'s 1 g frequency ({m} Hz) belongs to the motor\'s own cylinder; the value above is for the uploaded tank geometry.')
                : TF('panel.calkanti.f1Fark', { m: n(f1.motor, 4) },
                     'The motor card gives {m} Hz for the same quantity; the two differ and both are shown.')) + '</div>';
        }
        // Beyanlar
        const beyanlar = (t.beyan || []).slice();
        const tablo = t.tablo;
        if (tablo) {
            const satirKod = {};
            tablo.satirlar.forEach(function (s) { (s.sebep || []).forEach(function (k) { satirKod[k] = 1; }); });
            Object.keys(satirKod).forEach(function (k) { if (beyanlar.indexOf(k) < 0) beyanlar.push(k); });
        }
        ((t.zaman && t.zaman.sebep) || []).forEach(function (k) { if (beyanlar.indexOf(k) < 0) beyanlar.push(k); });
        html += kodListesi(T('panel.calkanti.beyanlar', 'Declarations behind these numbers'), beyanlar, 'dim');
        // Kaynaklar — ekranda insan metni; makine yolları (alan adresleri)
        // yalnız aktarım dosyasının künyesinde (ham anahtar ekrana basılmaz).
        const kayRows = [];
        kayRows.push([esc(T('panel.calkanti.kYogunluk', 'Density source')),
            esc(veri.motor_type === 'hybrid'
                ? T('panel.calkanti.kYogunlukHibrit', 'the motor\'s oxidizer-tank block: saturated N₂O liquid density at ignition')
                : T('panel.calkanti.kYogunlukSivi', 'the motor\'s propellant data for this tank (the density used to size the tank)'))]);
        kayRows.push([esc(T('panel.calkanti.kViskozite', 'Viscosity ν (wall damping)')),
            sayi(t.nu_m2_s) ? ns(t.nu_m2_s, 4) + ' m²/s — '
                + esc(T('panel.calkanti.kViskoziteKaynak', 'ν = μ/ρ with μ of the motor\'s feed-line model'))
                            : esc(T('panel.calkanti.kViskoziteYok', 'not published by the motor; wall damping not computed (taken as 0 in 6-DOF, conservative)'))]);
        if (t.geometri) {
            const gd = t.geometri_dosyasi;
            kayRows.push([esc(T('panel.calkanti.kGeometri', 'Tank geometry')),
                'R = ' + ns(t.geometri.R_ref_m, 5) + ' m, H = ' + ns(t.geometri.H_ic_m, 5) + ' m, V = '
                + ns(t.geometri.V_ic_m3, 5) + ' m³ — '
                + esc(gd ? TF('panel.calkanti.kGeoDosya', { file: gd.dosya_adi || '—', sha: (gd.sha256 || '—').slice(0, 12) },
                              'from the uploaded file {file} (sha256 {sha}…)')
                         : T('panel.calkanti.kGeoMotor', 'motor design: flat-capped upright cylinder, V = π/4·D²·L'))]);
        }
        if (sayi(t.motor_bafl_sonumu_tam_doluluk)) kayRows.push([esc(T('panel.calkanti.kMotorBafl', 'Motor\'s own baffle damping, full fill')),
            n(t.motor_bafl_sonumu_tam_doluluk, 5)]);
        html += u.kvTable(kayRows);
        kok.innerHTML = html;

        if (tablo) {
            frekansHaritasi(kok, t, i);
            modelEgrileri(kok, t, i);
            if (t.zaman && t.zaman.satirlar && t.zaman.satirlar.length) zamanGrafigi(kok, t, i);
            const kuyruk = document.createElement('div');
            kuyruk.innerHTML = tabloHtml(tablo) + yukHtml(t) + baflHtml(t) + indirHtml(t);
            kok.appendChild(kuyruk);
            kuyruk.querySelectorAll('[data-clk-indir]').forEach(function (b) {
                b.addEventListener('click', function () {
                    indir(b.getAttribute('data-clk-tank'), b.getAttribute('data-clk-indir'));
                });
            });
        }
        return kok;
    }

    function yukluSatir(t) {
        // Yüklü doluluğa EN YAKIN tablo satırı değil: sunucu bu dolulukta
        // f1'i tablonun ara değeriyle verdi; burada aynı satır aranmaz,
        // yalnız düğümse tablo satırı kullanılır. Değilse zaman ekseninin
        // t = 0 satırı (aynı ara değer) kullanılır.
        const z = t.zaman && t.zaman.satirlar;
        if (z && z.length && z[0].t_s === 0 && z[0].durum !== 'RET') return z[0];
        const s = (t.tablo.satirlar || []).filter(function (x) { return x.doluluk === t.yuklu_doluluk; })[0];
        return s && s.durum !== 'RET' ? s : null;
    }

    function frekansHaritasi(kok, t, i) {
        const h = t.frekans_haritasi;
        if (!h || typeof Plotly === 'undefined' || !Array.isArray(h.f1_hz) || !h.f1_hz.length) return;
        const div = document.createElement('div');
        div.id = 'clk_harita_' + i;
        kok.appendChild(div);
        const xb = T('panel.calkanti.axDoluluk', 'Fill fraction V_liquid/V_tank');
        const gs = h.g_eff_m_s2;
        if (gs.length === 1) {
            Plotly.newPlot(div, [{ x: h.doluluk, y: h.f1_hz.map(function (r) { return r[0]; }),
                type: 'scatter', mode: 'lines+markers', name: TF('panel.calkanti.trF1g', { g: ns(gs[0], 6) }, 'f1 at g_eff = {g} m/s²'),
                line: { color: '#00e5ff', width: 2 }, marker: { size: 5 } }],
                cizimDuzeni(T('panel.calkanti.chHarita', 'Slosh frequency f1 vs fill and effective axial acceleration'), xb, T('panel.calkanti.axF1', 'f1 (Hz)')),
                { responsive: true, displaylogo: false });
            return;
        }
        const z = gs.map(function (g, j) { return h.f1_hz.map(function (r) { return r[j]; }); });
        Plotly.newPlot(div, [{ x: h.doluluk, y: gs, z: z, type: 'heatmap', colorscale: 'Viridis',
            colorbar: { title: { text: T('panel.calkanti.axF1', 'f1 (Hz)'), font: { size: 13 } }, tickfont: { size: 12 } },
            hovertemplate: '%{x}<br>g = %{y}<br>f1 = %{z} Hz<extra></extra>' }],
            cizimDuzeni(T('panel.calkanti.chHarita', 'Slosh frequency f1 vs fill and effective axial acceleration'), xb,
                T('panel.calkanti.axGeff', 'Effective axial acceleration (m/s²)'), { margin: { t: 60, b: 70, l: 80, r: 40 } }),
            { responsive: true, displaylogo: false });
    }

    function modelEgrileri(kok, t, i) {
        if (typeof Plotly === 'undefined') return;
        const s = t.tablo.satirlar.filter(function (r) { return r.durum !== 'RET'; });
        if (!s.length) return;
        const x = s.map(function (r) { return r.doluluk; });
        const div = document.createElement('div');
        div.id = 'clk_model_' + i;
        kok.appendChild(div);
        Plotly.newPlot(div, [
            { x: x, y: s.map(function (r) { return r.L1_m; }), name: T('panel.calkanti.trL1', 'L1 pendulum length'),
              type: 'scatter', mode: 'lines', line: { color: '#00e5ff', width: 2 } },
            { x: x, y: s.map(function (r) { return r.z1_m; }), name: T('panel.calkanti.trZ1', 'z1 slosh-mass height'),
              type: 'scatter', mode: 'lines', line: { color: tokenRengi('var(--hd-amber-source, #ffb347)'), width: 2 } },
            { x: x, y: s.map(function (r) { return r.z_aski_m; }), name: T('panel.calkanti.trAski', 'hinge point z1 + L1'),
              type: 'scatter', mode: 'lines', line: { color: '#c792ea', width: 2, dash: 'dash' } },
            { x: x, y: s.map(function (r) { return r.m1_oran; }), name: T('panel.calkanti.trM1', 'm1/m slosh-mass ratio'),
              type: 'scatter', mode: 'lines', yaxis: 'y2', line: { color: '#2dd4a8', width: 2, dash: 'dot' } },
        ], cizimDuzeni(T('panel.calkanti.chModel', 'Equivalent model vs fill (independent of the effective axial acceleration)'),
            T('panel.calkanti.axDoluluk', 'Fill fraction V_liquid/V_tank'), T('panel.calkanti.axUzunluk', 'Height above tank bottom / length (m)'),
            { yaxis2: Object.assign(eksen(T('panel.calkanti.axOran', 'Mass ratio m1/m')), { overlaying: 'y', side: 'right', showgrid: false }) }),
            { responsive: true, displaylogo: false });
    }

    function zamanGrafigi(kok, t, i) {
        if (typeof Plotly === 'undefined') return;
        const z = t.zaman.satirlar;
        const div = document.createElement('div');
        div.id = 'clk_zaman_' + i;
        kok.appendChild(div);
        const izler = [{ x: z.map(function (r) { return r.t_s; }), y: z.map(function (r) { return r.doluluk; }),
            name: T('panel.calkanti.trDoluluk', 'Fill fraction'), type: 'scatter', mode: 'lines',
            line: { color: '#00e5ff', width: 2 } }];
        const ek = {};
        const f1Var = z.some(function (r) { return sayi(r.f1_hz); });
        if (f1Var) {
            izler.push({ x: z.map(function (r) { return r.t_s; }), y: z.map(function (r) { return sayi(r.f1_hz) ? r.f1_hz : null; }),
                name: TF('panel.calkanti.trF1g', { g: ns(t.zaman.g_eff_m_s2, 6) }, 'f1 at g_eff = {g} m/s²'),
                type: 'scatter', mode: 'lines', yaxis: 'y2', line: { color: tokenRengi('var(--hd-amber-source, #ffb347)'), width: 2, dash: 'dot' } });
            ek.yaxis2 = Object.assign(eksen(T('panel.calkanti.axF1', 'f1 (Hz)')), { overlaying: 'y', side: 'right', showgrid: false });
        }
        Plotly.newPlot(div, izler, cizimDuzeni(T('panel.calkanti.chZaman', 'Fill history from the motor\'s propellant consumption'),
            T('panel.calkanti.axZaman', 'Time from ignition (s)'), T('panel.calkanti.trDoluluk', 'Fill fraction'), ek),
            { responsive: true, displaylogo: false });
    }

    function tabloHtml(tablo) {
        const u = U();
        const bas = [['panel.calkanti.thDoluluk', 'Fill'], ['panel.calkanti.thH', 'h (m)'],
            ['panel.calkanti.thM', 'm liquid (kg)'], ['panel.calkanti.thM1', 'm1/m'], ['panel.calkanti.thL1', 'L1 (m)'],
            ['panel.calkanti.thZ1', 'z1 (m)'], ['panel.calkanti.thAski', 'hinge z1+L1 (m)'], ['panel.calkanti.thM0', 'm0/m'],
            ['panel.calkanti.thZ0', 'z0 (m)'], ['panel.calkanti.thZkm', 'liquid CG z (m)'],
            ['panel.calkanti.thIkm', 'I about CG, frozen (kg·m²)'], ['panel.calkanti.thGamma', 'Γ1'],
            ['panel.calkanti.thDurum', 'Status']];
        const th = bas.map(function (b) { return '<th style="' + u.TD + '">' + esc(T(b[0], b[1])) + '</th>'; }).join('');
        const tr = tablo.satirlar.map(function (s) {
            const h = [n(s.doluluk, 3), ns(s.h_m, 5), ns(s.m_sivi_kg, 5), ns(s.m1_oran, 4), ns(s.L1_m, 5),
                ns(s.z1_m, 5), ns(s.z_aski_m, 5), ns(s.m0_oran, 4), ns(s.z0_m, 5), ns(s.z_km_m, 5),
                ns(s.I_km_donmus_kgm2, 5), ns(s.Gamma1, 4), esc(durumMetni(s.durum))];
            return '<tr>' + h.map(function (c) { return '<td style="' + u.TD + '">' + c + '</td>'; }).join('') + '</tr>';
        }).join('');
        return '<details style="margin:8px 0;"><summary style="cursor:pointer; font-size:0.84rem;">'
            + esc(T('panel.calkanti.secTablo', 'Equivalent-model table (29 fill rows; positions above the tank bottom)'))
            + '</summary><div style="overflow-x:auto;"><table style="' + u.TBL + '"><tr>' + th + '</tr>' + tr
            + '</table></div></details>';
    }

    function yukHtml(t) {
        const u = U();
        const y = t.yukler;
        if (!y) return '';
        if (y.durum !== 'HESAPLANDI') {
            return u.sectionTitle(esc(T('panel.calkanti.secYuk', 'SP-8009 slosh loads, two amplitude levels')))
                + '<div style="font-size:0.82rem;">' + esc(T('panel.calkanti.hesaplanmadi', 'Not computed:'))
                + ' ' + esc((y.sebep || []).map(kodMetni).join(' ')) + '</div>';
        }
        const duz = [['dogrusal_sinir', 'panel.calkanti.yukDogrusal', 'linear limit, wall wave η = 0.2 R'],
                     ['kirilma_ust_siniri', 'panel.calkanti.yukKirilma', 'breaking upper bound, η = L1 (outside linear theory)']];
        const bas = [['panel.calkanti.thDoluluk', 'Fill'], ['panel.calkanti.thF1', 'F1 (N)'],
            ['panel.calkanti.thM1km', 'M1 about liquid CG (N·m)'], ['panel.calkanti.thPyuzey', 'wall pressure at surface, dynamic (Pa)'],
            ['panel.calkanti.thPtaban', 'bottom pressure (Pa, ullage excluded)']];
        let html = u.sectionTitle(esc(T('panel.calkanti.secYuk', 'SP-8009 slosh loads, two amplitude levels')))
            + '<div style="font-size:0.8rem;">' + esc(TF('panel.calkanti.yukG', { g: ns(y.g_eff_m_s2, 6) },
                'Loads at g_eff = {g} m/s² (the largest value given); they scale linearly with the effective axial acceleration. Tank fixed, free slosh (Dodge 2000 Eq. (3.4b), (3.5); NASA SP-8009 Eq. (4)).')) + '</div>';
        duz.forEach(function (d) {
            const b = y.duzeyler[d[0]];
            const th = bas.map(function (x) { return '<th style="' + u.TD + '">' + esc(T(x[0], x[1])) + '</th>'; }).join('');
            const tr = y.doluluk.map(function (dl, j) {
                return '<tr>' + [n(dl, 3), ns(b.F1_N[j], 5), ns(b.M1_km_Nm[j], 5), ns(b.p_dinamik_yuzey_Pa[j], 5),
                    ns(b.p_taban_Pa[j], 5)].map(function (c) { return '<td style="' + u.TD + '">' + c + '</td>'; }).join('') + '</tr>';
            }).join('');
            const kodlar = {};
            (b.sebep || []).forEach(function (l) { (l || []).forEach(function (k) { kodlar[k] = 1; }); });
            html += '<details style="margin:6px 0;"><summary style="cursor:pointer; font-size:0.82rem;">'
                + esc(T(d[1], d[2])) + '</summary><div style="overflow-x:auto;"><table style="' + u.TBL + '"><tr>' + th + '</tr>'
                + tr + '</table></div>'
                + (Object.keys(kodlar).length ? '<div style="font-size:0.78rem;">' + esc(Object.keys(kodlar).map(kodMetni).join(' ')) + '</div>' : '')
                + '</details>';
        });
        return html;
    }

    function baflHtml(t) {
        const u = U();
        const b = t.bafl;
        if (!b) return '';
        let html = u.sectionTitle(esc(T('panel.calkanti.secBafl', 'Ring-baffle recommendation (Miles, approximate)')));
        if (b.durum !== 'HESAPLANDI') {
            return html + '<div style="font-size:0.82rem;">' + esc(T('panel.calkanti.hesaplanmadi', 'Not computed:'))
                + ' ' + esc((b.sebep || []).map(kodMetni).join(' ')) + '</div>';
        }
        const o = b.oneri || {};
        const d = b.degerlendirme;
        const rows = [
            [esc(T('panel.calkanti.bDoluluk', 'Evaluated at the loaded fill')),
                n(b.doluluk, 4) + ' (h = ' + ns(b.h_m, 5) + ' m)'],
            [esc(T('panel.calkanti.bHedef', 'Target damping ratio')), n(o.target_damping_ratio, 4)],
            [esc(T('panel.calkanti.bDerinlik', 'Baffle depth below the surface d/R')), n(b.derinlik_orani, 3)],
            [esc(T('panel.calkanti.bGenislikOran', 'Recommended width w/R')), n(o.recommended_width_ratio, 4)],
            [esc(T('panel.calkanti.bGenislik', 'Recommended width w')), ns(o.recommended_width_m, 4) + ' m'],
        ];
        if (d) {
            rows.push([esc(T('panel.calkanti.bBant', 'Damping at this width, ×2 band (HRMA choice)')),
                n(d.damping_ratio, 4) + ' (' + n(d.damping_ratio_low, 4) + ' – ' + n(d.damping_ratio_high, 4) + ')']);
        } else {
            rows.push([esc(T('panel.calkanti.bUlasilamaz', 'Single baffle')),
                esc(T('panel.calkanti.bUlasilamazMetin', 'cannot reach the target; several baffles or wider rings are needed'))]);
        }
        html += u.kvTable(rows);
        const kodlar = (o.validity_codes || []).concat(d ? (d.validity_codes || []) : []);
        const tek = kodlar.filter(function (k, j) { return kodlar.indexOf(k) === j; });
        if (tek.length) html += '<div style="font-size:0.78rem;">' + esc(tek.map(kodMetni).join(' ')) + '</div>';
        html += '<div style="font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5);">'
            + esc(T('panel.calkanti.bNot', 'Single flat ring baffle near the free surface; damping falls as exp(−4.6 d/R) with depth, so more baffles are needed down the tank as the level drains. The ×2 band is an HRMA choice (Dodge 2000 Fig. 2.7 scatter).')) + '</div>';
        return html;
    }

    function indirHtml(t) {
        const u = U();
        const btn = function (bicim, key, text, ok) {
            return '<button type="button" class="btn" data-clk-indir="' + bicim + '" data-clk-tank="' + esc(t.tank_id) + '"'
                + (ok ? '' : ' disabled') + ' style="margin:4px 8px 4px 0;" data-i18n="' + key + '">' + esc(T(key, text)) + '</button>';
        };
        const zamanVar = !!(t.zaman && t.zaman.satirlar && t.zaman.satirlar.length);
        return u.sectionTitle(esc(T('panel.calkanti.secAktarim', 'Hand-off table for the vehicle team')))
            + '<div style="font-size:0.8rem;">' + esc(T('panel.calkanti.aktarimNot',
                'JSON holds the equivalent-model table (readable by the HRMA table reader), the time axis from the motor\'s consumption and the provenance lines; the fill CSV is the same table; the time CSV is the time axis. m0, m1, L1, hinge, ζ, liquid CG and inertia; positions in the tank frame (z up from the tank bottom).')) + '</div>'
            + btn('json', 'panel.calkanti.btnJson', 'Hand-off table (JSON)', true)
            + btn('csv_doluluk', 'panel.calkanti.btnCsvDoluluk', 'Fill table (CSV)', true)
            + btn('csv_zaman', 'panel.calkanti.btnCsvZaman', 'Time table (CSV)', zamanVar);
    }

    function ciz() {
        const sonuc = document.getElementById('clk_sonuc');
        const v = durumlar.sonVeri;
        if (!sonuc || !v) return;
        const u = U();
        if (u && u.purgePlots) u.purgePlots(sonuc);
        sonuc.innerHTML = '';
        const ust = document.createElement('div');
        let html = '';
        const gs = v.g_eff_m_s2 || [];
        html += '<div style="font-size:0.82rem; margin:4px 0;">'
            + esc(v.g_eff_kaynagi === 'varsayilan_g0'
                ? TF('panel.calkanti.geffVarsayilan', { g: ns(gs[0], 6) }, 'The effective axial acceleration was not given: standard gravity g0 = {g} m/s² (1 g) was used.')
                : gs.length > 1 ? TF('panel.calkanti.geffAralik', { lo: ns(gs[0], 6), hi: ns(gs[gs.length - 1], 6), k: gs.length },
                                     'Effective axial acceleration range {lo} – {hi} m/s², {k} equally spaced values.')
                : TF('panel.calkanti.geffTek', { g: ns(gs[0], 6) }, 'Effective axial acceleration = {g} m/s².'))
            + '</div>';
        if (v.motor_type === 'solid' || (v.sebep || []).indexOf('TANK_YOK') >= 0) {
            html += '<div style="margin:6px 0;">' + esc(T('panel.calkanti.katiSatir',
                'There is no liquid propellant in a solid motor; slosh does not apply.')) + '</div>';
        }
        ust.innerHTML = html;
        sonuc.appendChild(ust);
        (v.tanklar || []).forEach(function (t, i) { sonuc.appendChild(tankBolumu(t, i, v)); });
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(sonuc);
    }

    // Motor yeniden hesaplandı: eski sonuç yeni motora ait değildir.
    function motorDegisti() {
        const sonuc = document.getElementById('clk_sonuc');
        const st = document.getElementById('clk_durum');
        if (!durumlar.sonVeri) return;
        durumlar.sonVeri = null;
        durumlar.sonIstek = null;
        const u = U();
        if (sonuc) { if (u && u.purgePlots) u.purgePlots(sonuc); sonuc.innerHTML = ''; }
        if (st) st.textContent = T('panel.calkanti.bayat',
            'The motor was recalculated; the previous tank-model result belonged to the earlier motor and was cleared. Run it again.');
    }

    // ------------------------------------------------------------------
    // Montaj
    // ------------------------------------------------------------------
    function mount(pane) {
        if (!pane || pane.querySelector('#clk_bolum')) return false;
        const mt = motorTuru();
        if (mt !== 'liquid' && mt !== 'hybrid') return false;
        const kap = document.createElement('div');
        kap.id = 'clk_bolum';
        kap.style.cssText = 'border-top:1px solid var(--hd-line-strong, rgba(0,229,255,0.42)); margin-top:16px; padding-top:8px;';
        kap.innerHTML = '<h4 style="margin:6px 0 4px;" data-i18n="panel.calkanti.secTitle">'
            + esc(T('panel.calkanti.secTitle', 'Tank slosh model — equivalent model vs fill, frequency map, loads and hand-off table')) + '</h4>'
            + '<p style="font-size:0.8rem; margin:2px 0 6px;" data-i18n="panel.calkanti.intro">'
            + esc(T('panel.calkanti.intro', 'Built from this motor\'s own tanks: the equivalent mechanical model over the fill fraction (Dodge 2000, NASA SP-8009), the fill history from the motor\'s propellant consumption, the slosh loads and a baffle recommendation. Positions are in the tank frame; the tank\'s place in the vehicle is entered in the 6-DOF panel.')) + '</p>'
            + '<p style="font-size:0.8rem; margin:2px 0 6px; color:var(--hd-orange, #ff8c33);" data-i18n="panel.calkanti.kapsamDisi">'
            + esc(T('panel.calkanti.kapsamDisi', 'Control loop not modelled; for a guided vehicle this coupling is the main risk, and the hand-off table is meant for the vehicle team\'s GNC tool.')) + '</p>'
            + formHtml(mt)
            + '<div id="clk_durum" style="font-family:var(--hd-mono); color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>'
            + '<div id="clk_sonuc"></div>';
        pane.appendChild(kap);
        durumlar.kok = kap;
        const b = kap.querySelector('#clk_hesapla');
        if (b) b.addEventListener('click', hesapla);
        const y = kap.querySelector('#clk_geo_yukle');
        if (y) y.addEventListener('click', geometriYukle);
        if (window.I18N && window.I18N.onChange) window.I18N.onChange(function () {
            ciz();
            geometriListesi();
        });
        return true;
    }

    // Katı motor: Besleme bölümünün başında tek satır (sekme yok).
    function mountSolid(root) {
        if (!root || root.querySelector('#clk_kati')) return false;
        const p = document.createElement('p');
        p.id = 'clk_kati';
        p.setAttribute('data-i18n', 'panel.calkanti.katiSatir');
        p.style.cssText = 'font-size:0.82rem; margin:6px 0;';
        p.textContent = T('panel.calkanti.katiSatir', 'There is no liquid propellant in a solid motor; slosh does not apply.');
        root.insertBefore(p, root.firstChild);
        return true;
    }

    // ==================================================================
    // 6-DOF "Kararlılık" bölümünün çalkantı alt bölümü (CALKANTI §B.1, §B.5)
    // ------------------------------------------------------------------
    // Form tankın araçtaki yerini ister: varsayılan yöntem "ardışık dizilim"
    // (uçuş modelinin gövde kuralı; BEYANLI), sıra kullanıcıdan. Sıra ya da
    // istasyon girilmedikçe blok gönderilmez: "tank yeri girilmedi",
    // çalkantı bağlanmaz, 6-DOF bugünküyle aynı (uydurma konum yok).
    // Sonuçta künye en üstte, tank durumu ve beyanlar, zaman alanı
    // grafikleri. Kararlılık HÜKMÜ ve pencere tablosu bu sürümde basılmaz
    // (hüküm sözleşmesi ayrı kulvarda); alanı da çizilmez.
    // ==================================================================
    const sd = { veri: null };

    function sdTanklar(mt) { return mt === 'liquid' ? ['oksitleyici', 'yakit'] : ['n2o']; }

    function sixdofForm(kok) {
        if (!kok || kok.querySelector('#sd_clk_bolum')) return false;
        const mt = motorTuru();
        const kap = document.createElement('div');
        kap.id = 'sd_clk_bolum';
        kap.style.cssText = 'border:1px solid var(--hd-line, rgba(0,229,255,0.14)); border-radius:8px; padding:8px 12px; margin:8px 0;';
        if (mt !== 'liquid' && mt !== 'hybrid') {
            kap.innerHTML = '<div style="font-size:0.82rem;" data-i18n="panel.calkanti.katiSatir">'
                + esc(T('panel.calkanti.katiSatir', 'There is no liquid propellant in a solid motor; slosh does not apply.')) + '</div>';
            kok.appendChild(kap);
            return true;
        }
        const tanklar = sdTanklar(mt);
        // V307/UÇUŞ-GÖVDE: varsayılan sıra motorun tank listesi sırasıdır
        // (oksitleyici önde) — türetilmiş gövdenin kurulduğu dizilim; örnek
        // motorda kullanıcı hiçbir şey girmeden çalkantı bağlanır. "Girilmedi"
        // seçilirse uçuş rijit kalır.
        const siralar = mt === 'liquid'
            ? [['oksitleyici,yakit', 'Oxidizer forward, fuel aft', 'panel.calkanti.sd.siraOksOnde'],
               ['yakit,oksitleyici', 'Fuel forward, oxidizer aft', 'panel.calkanti.sd.siraYakitOnde'],
               ['', 'Not entered (slosh is not coupled)', 'panel.calkanti.sd.siraYok']]
            : [['n2o', 'N₂O tank directly ahead of the motor', 'panel.calkanti.sd.siraN2o'],
               ['', 'Not entered (slosh is not coupled)', 'panel.calkanti.sd.siraYok']];
        const yerler = [['ardisik', 'Sequential arrangement (declared)', 'panel.calkanti.sd.yerArdisik'],
                        ['istasyon', 'Tank bottom stations (m from the nose)', 'panel.calkanti.sd.yerIstasyon']];
        let html = '<div style="font-weight:600; margin:2px 0 4px;" data-i18n="panel.calkanti.sd.formBaslik">'
            + esc(T('panel.calkanti.sd.formBaslik', 'Slosh — where the tanks sit in the vehicle')) + '</div>'
            + '<div style="font-size:0.78rem; margin:2px 0 6px;" data-i18n="panel.calkanti.sd.formNot">'
            + esc(T('panel.calkanti.sd.formNot', 'By default the tanks sit where the derived airframe puts them: directly ahead of the motor, in the order of the engine tank list, each with its inner length and end closures (declared). If the body cannot carry a tank, that tank is not coupled and the reason is named. Choose "Not entered" to fly the vehicle rigid. A tank geometry uploaded in the Feed System slosh tab is used here too.')) + '</div>'
            + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:10px;">'
            + '<div class="form-group">' + alanBasi('panel.calkanti.sd.fYer', 'Tank location source',
                'panel.calkanti.help.sd_yer',
                'Where the tank positions come from. Sequential arrangement (default, declared): the tanks sit directly ahead of the motor in the order you choose, inside this vehicle\'s body; each tank takes its inner length plus the two end closure thicknesses the engine publishes, neighbouring closures in contact (the rule the derived airframe is built with). Tank bottom stations: you give each tank\'s bottom station in metres from the nose. It sets the slosh arm ξ about the vehicle centre of gravity. Order or station not entered: the tank is not coupled.',
                'sd_clk_yer')
            + '<select id="sd_clk_yer">' + secenekler(yerler, 'ardisik') + '</select></div>'
            + '<div class="form-group" data-sd-clk="ardisik">' + alanBasi('panel.calkanti.sd.fSira', 'Order from nose to tail',
                'panel.calkanti.help.sd_sira',
                'Order of the tanks from the nose to the tail for the sequential arrangement. It decides which tank is further from the centre of gravity, which changes the slosh moment arm. Default: the order of the engine tank list (oxidizer forward), the order the derived airframe is built with. Not entered: the tanks are not coupled and the 6-DOF result is the rigid one. Each tank of the motor appears once.',
                'sd_clk_sira')
            + '<select id="sd_clk_sira">' + secenekler(siralar, siralar[0][0]) + '</select></div>';
        tanklar.forEach(function (tid) {
            const a = TANK_ADI[tid];
            html += '<div class="form-group" data-sd-clk="istasyon" style="display:none;">'
                + '<div class="ad-field-head"><label for="sd_clk_x_' + tid + '">'
                + '<span data-i18n="' + a[0] + '">' + esc(T(a[0], a[1])) + '</span>'
                + ' — <span data-i18n="panel.calkanti.sd.fIstasyon">' + esc(T('panel.calkanti.sd.fIstasyon', 'bottom station x (m)')) + '</span></label>'
                + yardim('panel.calkanti.help.sd_istasyon',
                    'Station of the tank bottom (the tank end facing the tail) in metres from the nose, positive toward the tail. It sets the slosh moment arm ξ about the vehicle centre of gravity. Accepted: the tank top at or behind the nose cone, the bottom at or ahead of the body length, the tank no wider than the body, no overlap with another tank; otherwise the tank is not coupled and the reason is named. Blank: this tank is not coupled.')
                + '</div><input type="number" id="sd_clk_x_' + tid + '" step="0.01" min="0" value=""></div>';
        });
        html += '</div><div id="sd_clk_durum" style="font-size:0.8rem; margin:4px 0;"></div>';
        kap.innerHTML = html;
        kok.appendChild(kap);
        const yer = kap.querySelector('#sd_clk_yer');
        const goster = function () {
            const v = yer.value;
            kap.querySelectorAll('[data-sd-clk]').forEach(function (e) {
                e.style.display = (e.getAttribute('data-sd-clk') === v) ? '' : 'none';
            });
            sdDurumYaz();
        };
        yer.addEventListener('change', goster);
        kap.querySelectorAll('select, input').forEach(function (e) {
            e.addEventListener('change', sdDurumYaz);
            e.addEventListener('input', sdDurumYaz);
        });
        goster();
        return true;
    }

    function sdDuzen() {
        const mt = motorTuru();
        const yer = document.getElementById('sd_clk_yer');
        if (!yer) return null;
        if (yer.value === 'ardisik') {
            const s = document.getElementById('sd_clk_sira');
            if (!s || !s.value) return null;
            return { ardisik: { sira: s.value.split(',') } };
        }
        const ist = {};
        sdTanklar(mt).forEach(function (tid) {
            const v = sayiAlan('sd_clk_x_' + tid);
            if (v !== null) ist[tid] = v;
        });
        return Object.keys(ist).length ? { tank_istasyonlari: ist } : null;
    }

    function sdDurumYaz() {
        const el = document.getElementById('sd_clk_durum');
        if (!el) return;
        // V307/UÇUŞ-GÖVDE: anahtar elemana da yazılır (data-i18n). ÖLÇÜLDÜ
        // (tarayıcı, TR 1280): form sözlük yüklenmeden kurulunca bu satır TR
        // sayfada İngilizce kalıyordu (dil değişmediği için onChange gelmiyor);
        // sözlüğün applyTo geçişi artık onu da çevirir.
        const var_ = !!sdDuzen();
        const anahtar = var_ ? 'panel.calkanti.sd.yerVar' : 'panel.calkanti.sd.yerYok';
        el.setAttribute('data-i18n', anahtar);
        el.textContent = var_ ? T('panel.calkanti.sd.yerVar',
            'Tank location entered; the next 6-DOF run couples slosh to the flight.')
            : T('panel.calkanti.sd.yerYok', 'Tank location not entered; slosh is not coupled to the 6-DOF (no position is assumed).');
    }

    // 6-DOF isteğine eklenecek blok ya da null (yer girilmedi / katı /
    // motor sonucu yok). Sayfa motorunun uçup uçmadığına 6-DOF paneli bakar.
    function sixdofBlok() {
        const mt = motorTuru();
        if ((mt !== 'liquid' && mt !== 'hybrid') || !window.currentResults) return null;
        const duzen = sdDuzen();
        if (!duzen) return null;
        const b = { motor_type: mt, motor_sonucu: window.currentResults, arac_duzeni: duzen };
        const g = {};
        Object.keys(durumlar.geometriler).forEach(function (tid) {
            const k = durumlar.geometriler[tid];
            g[tid] = { profil_rz_m: k.profil_rz_m, dosya_adi: k.dosya_adi, sha256: k.sha256, sebep: k.sebep };
        });
        if (Object.keys(g).length) b.tank_geometrileri = g;
        return b;
    }

    function sixdofTemizle() {
        sd.veri = null;
        const uy = document.getElementById('sd_clk_gecersiz_uyari');
        if (uy) uy.remove();
        const hn = document.getElementById('sd_clk_hukum_notu');
        if (hn) hn.remove();
        const el = document.getElementById('sd_calkanti_sonuc');
        const u = U();
        if (el) { if (u && u.purgePlots) u.purgePlots(el); el.innerHTML = ''; }
    }

    function sdCizgi(div, izler, baslik, y, ek, t0) {
        const e = Object.assign({}, ek || {});
        const sekil = gecersizSekil(t0, seriSonu(izler));
        if (sekil) {
            e.shapes = (e.shapes || []).concat([sekil]);
        }
        Plotly.newPlot(div, izler, cizimDuzeni(baslik, T('panel.calkanti.sd.axZaman', 'Flight time (s)'), y, e),
            { responsive: true, displaylogo: false });
    }

    // ==================================================================
    // ÇALKANTI-KARARLILIK hüküm sözleşmesi (HUKUM_SOZLESMESI.md) — 6-DOF
    // Kararlılık çalkantı alt bölümünün HÜKÜM kısmı. Kodlar sözlükten EN +
    // TR metne çevrilir; ham kod basılmaz. Genel hüküm yanma boyunca
    // taramanın en kötü penceresinden gelir; dört an yalnız tabloda.
    // ==================================================================
    const HK = {
        hukum: {
            UYGULANMAZ: ['panel.calkanti.hk.hukum.UYGULANMAZ', 'DOES NOT APPLY', 'dim'],
            HUKUM_YOK: ['panel.calkanti.hk.hukum.HUKUM_YOK', 'NO VERDICT', 'dim'],
            RIJIT_GOVDE_KARARSIZ: ['panel.calkanti.hk.hukum.RIJIT_GOVDE_KARARSIZ', 'RIGID BODY UNSTABLE', 'err'],
            CALKANTI_KAYNAKLI_KARARSIZLIK: ['panel.calkanti.hk.hukum.CALKANTI_KAYNAKLI_KARARSIZLIK', 'SLOSH-INDUCED INSTABILITY', 'err'],
            KARARLI: ['panel.calkanti.hk.hukum.KARARLI', 'STABLE', 'ok'],
        },
        gerekce: {
            YANMA_ICI_CALKANTI_KARARSIZLIK_PENCERESI: ['panel.calkanti.hk.gerekce.YANMA_ICI_CALKANTI_KARARSIZLIK_PENCERESI',
                'During the burn there is at least one window in which a slosh mode grows while the rigid body is stable.'],
            YANMA_ICI_PENCERE_YALNIZ_SINIR_ASIMINDAN_SONRA: ['panel.calkanti.hk.gerekce.YANMA_ICI_PENCERE_YALNIZ_SINIR_ASIMINDAN_SONRA',
                'The scan found slosh-instability windows, but all of them come from samples after the first linear-limit exceedance, whose flight state belongs to a run outside the validity of the linear model.'],
            YANMA_ICI_RIJIT_GOVDE_KARARSIZ: ['panel.calkanti.hk.gerekce.YANMA_ICI_RIJIT_GOVDE_KARARSIZ',
                'No slosh window; the rigid body itself is unstable over an interval of the burn.'],
            TARAMADA_KARARSIZLIK_YOK: ['panel.calkanti.hk.gerekce.TARAMADA_KARARSIZLIK_YOK',
                'Every scanned sample where a verdict can be given is stable (coverage below).'],
            TARAMA_DEGERLENDIRILEMEDI: ['panel.calkanti.hk.gerekce.TARAMA_DEGERLENDIRILEMEDI',
                'No scanned sample allows a verdict; the reasons are listed.'],
            SAYISAL_TUTARSIZLIK: ['panel.calkanti.hk.gerekce.SAYISAL_TUTARSIZLIK',
                'At the worst point of a window the eigenvalues and the Hurwitz test disagree; no verdict is given.'],
            COZUM_YAKINSAMADI: ['panel.calkanti.hk.gerekce.COZUM_YAKINSAMADI',
                'The 6-DOF solution did not converge; no verdict is given.'],
            UCUS_APOJEYE_VARMADI: ['panel.calkanti.hk.gerekce.UCUS_APOJEYE_VARMADI',
                'The scan found no instability window, but the flight did not reach apogee: a STABLE verdict is not given for a flight that did not reach apogee.'],
            TANK_YOK: ['panel.calkanti.hk.gerekce.TANK_YOK',
                'There is no liquid propellant in a solid motor; slosh does not apply.'],
            TANK_BAGLANMADI: ['panel.calkanti.hk.gerekce.TANK_BAGLANMADI',
                'No tank could be coupled to the 6-DOF.'],
        },
        sebep: {
            RAYDA: ['panel.calkanti.hk.sebep.RAYDA', 'on the rail'],
            DONDURULMUS_KATSAYI_GECERSIZ: ['panel.calkanti.hk.sebep.DONDURULMUS_KATSAYI_GECERSIZ',
                'frozen-coefficient criterion not met (dynamic pressure changes too fast, ω_g·τ_q < 2π)'],
            CALKANTI_KAPALI: ['panel.calkanti.hk.sebep.CALKANTI_KAPALI', 'slosh switched off (no liquid model at this point)'],
            KALKIS_ANI_ALFA_TANIMSIZ: ['panel.calkanti.hk.sebep.KALKIS_ANI_ALFA_TANIMSIZ', 'angle of attack undefined at lift-off'],
            AN_ULASILMADI: ['panel.calkanti.hk.sebep.AN_ULASILMADI', 'instant not reached'],
            UCUS_APOJEYE_VARMADI: ['panel.calkanti.hk.sebep.UCUS_APOJEYE_VARMADI', 'flight did not reach apogee'],
            COZUM_YAKINSAMADI: ['panel.calkanti.hk.sebep.COZUM_YAKINSAMADI', 'solution did not converge'],
            SAYISAL_TUTARSIZLIK: ['panel.calkanti.hk.sebep.SAYISAL_TUTARSIZLIK', 'eigenvalues and Hurwitz test disagree'],
            TANK_YOK: ['panel.calkanti.hk.sebep.TANK_YOK', 'no liquid tank'],
            TANK_BAGLANMADI: ['panel.calkanti.hk.sebep.TANK_BAGLANMADI', 'no tank coupled'],
        },
        // V307/UÇUŞ-GÖVDE: uçuşun nasıl bittiği (hükümden ayrı bilgi) ve
        // pencerenin doğrusal sınırın ilk aşımına göre yeri.
        ucus: {
            apogee: ['panel.calkanti.hk.ucus.apogee', 'apogee reached'],
            tumble: ['panel.calkanti.hk.ucus.tumble', 'tumble: the body rate passed the tumble threshold'],
            ground_impact_under_power: ['panel.calkanti.hk.ucus.ground_impact_under_power', 'ground impact while the motor was burning'],
            ground_impact_before_apogee: ['panel.calkanti.hk.ucus.ground_impact_before_apogee', 'ground impact before apogee'],
            no_liftoff: ['panel.calkanti.hk.ucus.no_liftoff', 'no lift-off'],
            time_limit: ['panel.calkanti.hk.ucus.time_limit', 'integration time limit reached'],
            solver_failed: ['panel.calkanti.hk.ucus.solver_failed', 'the solution did not converge'],
        },
        konum: {
            ASIMDAN_ONCE: ['panel.calkanti.hk.konum.ASIMDAN_ONCE', 'before the first linear-limit exceedance'],
            ASIMI_KAPSIYOR: ['panel.calkanti.hk.konum.ASIMI_KAPSIYOR', 'spans the first linear-limit exceedance'],
            ASIMDAN_SONRA: ['panel.calkanti.hk.konum.ASIMDAN_SONRA', 'after the first linear-limit exceedance: its flight state comes from a run outside linear validity'],
        },
        kenar: {
            ISARET_DEGISIMI: ['panel.calkanti.hk.kenar.ISARET_DEGISIMI', 'stable/unstable crossing (±1 ms)'],
            DEGERLENDIRME_SINIRI: ['panel.calkanti.hk.kenar.DEGERLENDIRME_SINIRI', 'edge of the evaluable region'],
        },
        an: {
            kalkis: ['panel.calkanti.hk.an.kalkis', 'Lift-off'],
            ray_cikisi: ['panel.calkanti.hk.an.ray_cikisi', 'Rail exit'],
            en_buyuk_q: ['panel.calkanti.hk.an.en_buyuk_q', 'Peak dynamic pressure in the burn'],
            yanma_sonu: ['panel.calkanti.hk.an.yanma_sonu', 'Burnout'],
        },
        mod: {
            calkanti: ['panel.calkanti.hk.mod.calkanti', 'slosh mode'],
            govde: ['panel.calkanti.hk.mod.govde', 'body (weathercock) mode'],
        },
    };
    function hk(tablo, kod) {
        const a = HK[tablo] && HK[tablo][kod];
        return a ? T(a[0], a[1]) : T('panel.calkanti.kodTaninmadi',
            'A reason code this screen does not know was returned; the result is not shown as valid.');
    }
    function evetHayir(v) {
        return v ? T('panel.calkanti.hk.evet', 'yes') : T('panel.calkanti.hk.hayir', 'no');
    }
    // Hücreler kelimeyi ortadan bölmez (güvertenin TD biçemi 'anywhere'
    // kırar: "Örne k"); sayı hücresi tek satır, tablo kabında yatay kaydırma.
    const KIRMA_YOK = ' overflow-wrap:normal; word-break:normal;';
    function th(key, text) {
        const u = U();
        return '<th style="' + u.TD + KIRMA_YOK + '">' + esc(T(key, text)) + '</th>';
    }
    function td(v) { return '<td style="' + U().TD + KIRMA_YOK + ' white-space:nowrap;">' + v + '</td>'; }
    function tdMetin(v) { return '<td style="' + U().TD + KIRMA_YOK + '">' + v + '</td>'; }

    function hukumHtml(h) {
        const u = U();
        let html = '';
        const hd = HK.hukum[h.genel_hukum];
        html += '<div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:6px 0;">'
            + u.badge(esc(T('panel.calkanti.hk.rozet', 'SLOSH STABILITY')) + ': ' + esc(hk('hukum', h.genel_hukum)),
                      hd ? hd[2] : 'dim')
            + '<span style="font-size:0.84rem;">' + esc(hk('gerekce', h.gerekce_kodu)) + '</span></div>';
        if (Array.isArray(h.sebep) && h.sebep.length) {
            html += '<div style="font-size:0.8rem;">' + esc(T('panel.calkanti.hk.sebepBaslik', 'Why no verdict could be given:'))
                + ' ' + esc(h.sebep.map(function (k) { return hk('sebep', k); }).join('; ')) + '</div>';
        }
        // V307/UÇUŞ-GÖVDE (kalem 5): uçuş apojeye varmadıysa bu AYRI cümleyle
        // yazılır; hüküm doğrusal taramanın bulgusudur, uçuşun neden sona
        // erdiğini söylemez. Sayılar yanıttan (ucus_sonu).
        const us = h.ucus_sonu;
        // Uçuşun sonu ilk doğrusal sınır aşımından sonraysa o son, koşunun
        // geçerlilik dışı bölümündendir (adıyla söylenir).
        const dsU = h.dogrusal_sinir;
        const sonGecersiz = !!(us && dsU && dsU.asildi && sayi(dsU.t_ilk_asim_s) && sayi(us.t_son_s)
            && us.t_son_s > dsU.t_ilk_asim_s);
        const sonNotu = sonGecersiz ? ' ' + T('panel.calkanti.hk.sonGecersiz',
            'That end lies after the first linear-limit exceedance, in the part of the coupled run that is outside linear validity.') : '';
        if (us && us.apojeye_vardi === false && HK.ucus[us.ucus]) {
            html += '<div style="font-size:0.82rem; margin:4px 0; border-left:3px solid var(--hd-amber, #ffbe46); padding-left:8px;">'
                + esc(TF('panel.calkanti.hk.ucusSonu', { t: n(us.t_son_s, 2), nasil: hk('ucus', us.ucus) },
                    'The coupled flight did not reach apogee: it ended at t = {t} s ({nasil}). The verdict above is the finding of the frozen-coefficient linear scan over the burn; it does not say why the flight ended, and it does not mean that slosh caused it.')
                    + sonNotu)
                + '</div>';
        }
        // --- pencere tablosu
        const p = Array.isArray(h.pencereler) ? h.pencereler : [];
        if (p.length) {
            html += u.sectionTitle(esc(T('panel.calkanti.hk.pencereBaslik', 'Slosh-instability windows during the burn')));
            let t = '<div style="overflow-x:auto;"><table style="' + u.TBL + '"><tr>'
                + th('panel.calkanti.hk.thAralik', 'Interval t1 – t2 (s)')
                + th('panel.calkanti.hk.thMaxRe', 'Largest Re(λ) (1/s) at t (s)')
                + th('panel.calkanti.hk.thMod', 'Unstable mode / tank')
                + th('panel.calkanti.hk.thFrekans', 'Mode frequency (rad/s)')
                + th('panel.calkanti.hk.thYakinlik', 'Proximity Ω_slosh/Ω_body')
                + th('panel.calkanti.hk.thZetaMin', 'Required ζ_min')
                + th('panel.calkanti.hk.thZetaGercek', 'Actual ζ')
                + th('panel.calkanti.hk.thBuyume', 'Approximate modal growth exponent ∫Re dt')
                + th('panel.calkanti.hk.thOrnek', 'Samples') + '</tr>';
            p.forEach(function (w) {
                const kenar = [w.t1_kenar, w.t2_kenar].filter(function (k) { return k === 'DEGERLENDIRME_SINIRI'; }).length
                    ? '<br><span style="font-size:0.72rem;">' + esc(hk('kenar', 'DEGERLENDIRME_SINIRI')) + '</span>' : '';
                const zmin = (w.zeta_min === null || w.zeta_min === undefined)
                    ? esc(T('panel.calkanti.hk.zetaUstu', 'not reached even at 0.5'))
                    : n(w.zeta_min, 4) + (w.zeta_min_dogrulandi === false
                        ? ' (' + esc(T('panel.calkanti.hk.dogrulanmadi', 'not verified at every sample')) + ')' : '');
                const yak = sayi(w.yakinlik_orani)
                    ? n(w.yakinlik_orani, 3) + (w.yakinlik_uyarisi ? ' — ' + esc(T('panel.calkanti.hk.yakin', 'frequencies close')) : '')
                    : '—';
                const buyume = sayi(w.buyume_ussu)
                    ? esc(TF('panel.calkanti.hk.buyumeKat', { x: ns(w.buyume_ussu, 4), k: ns(Math.exp(w.buyume_ussu), 3) },
                             '{x} (e^x = {k}; frozen-coefficient approximate modal growth, not a guaranteed amplitude gain)'))
                    : '—';
                // Pencerenin doğrusal sınırın ilk aşımına göre yeri (yanıttan).
                let konum = '';
                if (HK.konum[w.sinir_asimi_konumu]) {
                    konum = '<br><span style="font-size:0.72rem;">' + esc(hk('konum', w.sinir_asimi_konumu));
                    if (w.sinir_asimi_konumu === 'ASIMI_KAPSIYOR' && sayi(w.buyume_ussu_sinir_oncesi)
                            && sayi(w.ornek_sayisi_sinir_oncesi)) {
                        konum += ' — ' + esc(TF('panel.calkanti.hk.konumOncesi',
                            { x: ns(w.buyume_ussu_sinir_oncesi, 4), n: String(w.ornek_sayisi_sinir_oncesi) },
                            'before it: growth exponent {x} over {n} samples'));
                    }
                    konum += '</span>';
                }
                t += '<tr>' + tdMetin(n(w.t1, 3) + ' – ' + n(w.t2, 3) + kenar + konum)
                    + td(ns(w.max_re, 4) + ' @ ' + n(w.t_max_re, 3))
                    + tdMetin(esc(hk('mod', w.mod)) + (w.tank_id ? ' — ' + esc(tankAdi(w.tank_id)) : ''))
                    + td(ns(w.mod_frekansi_rad_s, 4)) + tdMetin(yak) + tdMetin(zmin) + td(ns(w.zeta_gercek, 3))
                    + tdMetin(buyume) + td(sayi(w.ornek_sayisi) ? String(w.ornek_sayisi) : '—') + '</tr>';
            });
            html += t + '</table></div>';
            const pb = [];
            p.forEach(function (w) { (w.beyanlar || []).forEach(function (k) { if (pb.indexOf(k) < 0) pb.push(k); }); });
            html += kodListesi(T('panel.calkanti.hk.pencereBeyan', 'Window declarations'), pb, 'dim');
        }
        const rp = Array.isArray(h.rijit_pencereler) ? h.rijit_pencereler : [];
        if (rp.length) {
            html += u.sectionTitle(esc(T('panel.calkanti.hk.rijitBaslik', 'Intervals where the rigid body itself is unstable (note; the main verdict is the 6-DOF flight verdict)')))
                + u.kvTable(rp.map(function (w) {
                    return [n(w.t1, 3) + ' – ' + n(w.t2, 3) + ' s', esc(T('panel.calkanti.hk.thMaxReKisa', 'largest Re(λ)')) + ' ' + ns(w.max_re, 4) + ' 1/s'];
                }));
        }
        // --- dört an
        const da = Array.isArray(h.dort_an) ? h.dort_an : [];
        if (da.length) {
            html += u.sectionTitle(esc(T('panel.calkanti.hk.dortAnBaslik', 'Four instants (reporting only; they do not set the verdict)')));
            let t = '<div style="overflow-x:auto;"><table style="' + u.TBL + '"><tr>'
                + th('panel.calkanti.hk.thAn', 'Instant') + th('panel.calkanti.hk.thT', 't (s)')
                + th('panel.calkanti.hk.thHukum', 'Verdict at this instant') + th('panel.calkanti.hk.thSebep', 'Reason for no verdict')
                + th('panel.calkanti.hk.thMaxReKisa', 'largest Re(λ)') + th('panel.calkanti.hk.thZetaMin', 'Required ζ_min')
                + th('panel.calkanti.hk.thPencereIcinde', 'Inside a window') + '</tr>';
            da.forEach(function (a) {
                t += '<tr>' + tdMetin(esc(hk('an', a.an))) + td(n(a.t, 3)) + tdMetin(esc(hk('hukum', a.hukum)))
                    + tdMetin(a.sebep ? esc(hk('sebep', a.sebep)) : '—') + td(ns(a.max_re, 4))
                    + td(ns(a.zeta_min, 4)) + td(esc(evetHayir(a.pencere_icinde))) + '</tr>';
            });
            html += t + '</table></div>';
        }
        // --- tarama kapsamı
        const kp = h.tarama && h.tarama.kapsam;
        if (kp) {
            html += '<div style="font-size:0.8rem; margin:6px 0;">' + esc(TF('panel.calkanti.hk.kapsam', {
                n: sayi(kp.ornek_sayisi) ? String(kp.ornek_sayisi) : '—', sure: n(kp.hukum_verilen_sure_s, 2),
                tb: n(kp.yanma_suresi_s, 2), oran: n(100 * kp.hukum_verilen_oran, 1) },
                'Scan over the burn: {n} solution samples; a verdict could be given for {sure} s of the {tb} s burn ({oran} %).')) + '</div>';
            // V307/UÇUŞ-GÖVDE (kalem 5): tarama aralığı, ilk doğrusal sınır
            // aşımı ve uçuşun bittiği an (hepsi yanıttan; yoksa satır yok).
            const ar = h.tarama.aralik;
            const dsA = h.dogrusal_sinir;
            if (ar && sayi(ar.t_bas_s) && sayi(ar.t_son_s) && us && sayi(us.t_son_s) && HK.ucus[us.ucus] && dsA) {
                html += '<div style="font-size:0.8rem; margin:4px 0;">' + esc(TF('panel.calkanti.hk.aralik', {
                    t0: n(ar.t_bas_s, 2), t1: n(ar.t_son_s, 2), ts: n(us.t_son_s, 2), nasil: hk('ucus', us.ucus),
                    asim: (dsA.asildi && sayi(dsA.t_ilk_asim_s))
                        ? TF('panel.calkanti.hk.aralikAsim', { t: n(dsA.t_ilk_asim_s, 2) }, 't = {t} s')
                        : T('panel.calkanti.hk.aralikAsimYok', 'none') },
                    'Scan interval: {t0} – {t1} s. First linear-limit exceedance: {asim}. End of the coupled flight: t = {ts} s ({nasil}).')
                    + sonNotu) + '</div>';
            }
            const hv = (kp.hukum_verilemeyen || []).map(function (a) {
                const kod = (a.kodlar || []).map(kodMetni).join(' ');
                return n(a.t1, 3) + ' – ' + n(a.t2, 3) + ' s: ' + hk('sebep', a.sebep) + (kod ? ' — ' + kod : '');
            });
            if (hv.length) html += u.listBlock(esc(T('panel.calkanti.hk.verilemeyen', 'Intervals without a verdict')), hv, 'dim');
        }
        // --- doğrusal sınır
        const ds = h.dogrusal_sinir;
        if (ds) {
            if (ds.asildi) {
                html += '<div style="border:1px solid var(--hd-red, #ff5d73); border-radius:8px; padding:8px 12px; margin:8px 0; font-size:0.82rem;">'
                    + esc(TF('panel.calkanti.hk.dogrusalAsildi', {
                        t: n(ds.t_ilk_asim_s, 3), tank: ds.tank_id_ilk_asim ? tankAdi(ds.tank_id_ilk_asim) : '—',
                        sinir: n(ds.sinir, 2), oncesi: ns(ds.max_eta_R_sinir_oncesi, 4) },
                        'The wall wave amplitude passed the linear limit η/R = {sinir} at t = {t} s ({tank}). From that point on the slosh amplitude, force and moment are outside the validity of the linear model and are marked as such; the apogee, speed, angle of attack and drift of the coupled run are not reported. Largest η/R before the limit: {oncesi}.')) + '</div>';
            } else {
                html += '<div style="font-size:0.8rem; margin:4px 0;">' + esc(TF('panel.calkanti.hk.dogrusalIcinde', {
                    m: ns(ds.max_eta_R, 3), sinir: n(ds.sinir, 2) },
                    'The wall wave amplitude stayed inside the linear limit (largest η/R = {m}; limit {sinir}).')) + '</div>';
            }
        }
        html += baflOnerisiHtml(h.bafl_onerisi);
        html += kodListesi(T('panel.calkanti.hk.beyanlar', 'Declarations behind the verdict'), h.beyanlar || [], 'dim');
        return html;
    }

    function baflOnerisiHtml(b) {
        const u = U();
        if (!b) return '';
        let html = u.sectionTitle(esc(T('panel.calkanti.hk.baflBaslik', 'Ring-baffle recommendation that closes the window (Miles, approximate)')));
        if (!b.nominal && !b.tutucu) {
            return html + '<div style="font-size:0.82rem;">' + esc(kodMetni(b.sebep)) + '</div>';
        }
        html += '<div style="font-size:0.8rem;">' + esc(TF('panel.calkanti.hk.baflHedef', { z: ns(b.zeta_hedef, 4) },
            'Target damping ratio: {z} (the largest required ζ_min of the windows).')) + '</div>';
        let t = '<div style="overflow-x:auto;"><table style="' + u.TBL + '"><tr>'
            + th('panel.calkanti.hk.thDuzey', 'Design level') + th('panel.calkanti.hk.thTank', 'Propellant tank')
            + th('panel.calkanti.hk.thZetaTasarim', 'Design ζ') + th('panel.calkanti.hk.thGenislik', 'Width w/R (w, m)')
            + th('panel.calkanti.hk.thAralikHalka', 'Ring spacing s (m)') + th('panel.calkanti.hk.thHalka', 'Rings (heights above the bottom, m)')
            + th('panel.calkanti.hk.thYenidenTarama', 'Re-scan with this damping') + '</tr>';
        [['nominal', 'panel.calkanti.hk.duzeyNominal', 'nominal (Miles nominal reaches the target)'],
         ['tutucu', 'panel.calkanti.hk.duzeyTutucu', 'conservative (lower band edge reaches the target)']].forEach(function (d) {
            const dz = b[d[0]];
            if (!dz) return;
            (dz.tanklar || []).forEach(function (k) {
                const o = k.oneri;
                const yt = (dz.yeniden_tarama || {});
                const tarama = [['nominal', 'panel.calkanti.hk.ytNominal', 'nominal damping'],
                                ['alt_bant', 'panel.calkanti.hk.ytAltBant', 'lower band']].map(function (x) {
                    const r = yt[x[0]];
                    if (!r) return '';
                    return esc(T(x[1], x[2])) + ': ' + esc(r.pencere_kapandi
                        ? T('panel.calkanti.hk.kapandi', 'window closed')
                        : TF('panel.calkanti.hk.kalan', { k: String(r.pencere_sayisi), re: ns(r.max_re, 3) },
                             '{k} window(s) remain, largest Re(λ) {re} 1/s'));
                }).filter(Boolean).join('<br>');
                t += '<tr>' + tdMetin(esc(T(d[1], d[2]))) + tdMetin(esc(tankAdi(k.tank_id))) + td(ns(dz.zeta_tasarim, 4));
                if (o) {
                    t += td(n(o.width_ratio, 3) + ' (' + ns(o.width_m, 3) + ')') + td(ns(o.spacing_m, 3))
                        + tdMetin(String(o.halka_sayisi) + ': ' + (o.halka_yukseklikleri_m || []).map(function (z) { return ns(z, 3); }).join('; '));
                } else {
                    t += '<td colspan="3" style="' + u.TD + '">' + esc(kodMetni(k.sebep)) + '</td>';
                }
                t += tdMetin(tarama) + '</tr>';
            });
        });
        html += t + '</table></div>';
        html += '<div style="font-size:0.8rem; margin:4px 0;">'
            + esc(TF('panel.calkanti.hk.baflKapanma', { a: evetHayir(b.pencere_kapaniyor), b: evetHayir(b.pencere_kapaniyor_alt_bantta) },
                'Window closes with the nominal design at nominal damping: {a}; with the conservative design at the lower band: {b}.')) + '</div>'
            + '<div style="font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5);">'
            + esc(TF('panel.calkanti.hk.baflKaynak', { genlik: n(b.genlik_orani, 2), bant: n(b.bant_carpani, 0), aralik: n(b.aralik_orani, 4) },
                'Flat ring baffles, Miles 1958 (Dodge 2000 Eq. (2.16)); design amplitude η/R = {genlik}, ×{bant} band and ring spacing s/R = {aralik} are HRMA choices.')) + '</div>';
        html += kodListesi(T('panel.calkanti.hk.baflBeyan', 'Baffle declarations'), b.beyanlar || [], 'dim');
        return html;
    }

    // Tarama grafiği: max Re(t), bağlaşık ve rijit (hüküm verilemeyen
    // örnekte null — çizilmez).
    function taramaGrafigi(el, h) {
        const s = h.tarama && h.tarama.seri;
        if (!s || !Array.isArray(s.t) || !s.t.length || typeof Plotly === 'undefined') return;
        const d = document.createElement('div');
        d.id = 'sd_clk_tarama';
        el.appendChild(d);
        const izler = [
            { x: s.t, y: s.max_re, name: T('panel.calkanti.hk.trMaxRe', 'largest Re(λ), coupled'), type: 'scatter', mode: 'lines',
              line: { color: tokenRengi('var(--hd-red, #ff5d73)'), width: 2 } },
            { x: s.t, y: s.rijit_max_re, name: T('panel.calkanti.hk.trRijitMaxRe', 'largest Re(λ), rigid body'), type: 'scatter', mode: 'lines',
              line: { color: '#00e5ff', width: 1.5, dash: 'dot' } },
        ];
        const sekil = [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0, line: { color: '#7d97a5', width: 1 } }];
        (h.pencereler || []).forEach(function (w) {
            sekil.push({ type: 'rect', xref: 'x', yref: 'paper', x0: w.t1, x1: w.t2, y0: 0, y1: 1,
                         fillcolor: 'rgba(255,92,122,0.12)', line: { width: 0 } });
        });
        Plotly.newPlot(d, izler, cizimDuzeni(T('panel.calkanti.hk.chTarama', 'Growth rate over the burn (positive = growing)'),
            T('panel.calkanti.sd.axZaman', 'Flight time (s)'), T('panel.calkanti.hk.axRe', 'Largest Re(λ) (1/s)'), { shapes: sekil }),
            { responsive: true, displaylogo: false });
    }

    // Doğrusal sınır aşıldıysa iz geçerli ve geçersiz parçalara ayrılır:
    // geçersiz parça kesik ve soluk, adı "doğrusal model geçerliliği dışında".
    function maskeliIzler(izler, maske) {
        if (!Array.isArray(maske) || maske.every(Boolean)) return izler;
        const out = [];
        izler.forEach(function (iz) {
            const gecerli = Object.assign({}, iz, { y: iz.y.map(function (v, j) { return maske[j] ? v : null; }) });
            const disi = Object.assign({}, iz, {
                y: iz.y.map(function (v, j) { return (!maske[j] || (j + 1 < maske.length && !maske[j + 1])) ? v : null; }),
                name: iz.name + ' — ' + T('panel.calkanti.hk.gecersizIz', 'outside the validity of the linear model'),
                opacity: 0.4, line: Object.assign({}, iz.line || {}, { dash: 'dash' }),
            });
            out.push(gecerli, disi);
        });
        return out;
    }
    // Serinin son zamanı (izlerin x dizilerinin son sonlu değerlerinin en
    // büyüğü); yoksa null.
    function seriSonu(izler) {
        let son = null;
        (izler || []).forEach(function (iz) {
            const x = (iz && Array.isArray(iz.x)) ? iz.x : [];
            for (let j = x.length - 1; j >= 0; j--) {
                if (sayi(x[j])) {
                    if (son === null || x[j] > son) son = x[j];
                    break;
                }
            }
        });
        return son;
    }
    // Doğrusal geçerlilik dışı bölgenin gölgesi: ilk aşımdan serinin SONUNA
    // kadar. V307/UÇUŞ-GÖVDE: eski sağ kenar 1e9 s idi; Plotly eksen
    // otomatik aralığına şekilleri de kattığı için zaman ekseni milyar
    // saniyeye açılıyor, çizgiler eksenin başında görünmez kalıyordu
    // (ölçüldü: örnek sıvı motor, beş çalkantı grafiği + irtifa ve hücum
    // açısı grafikleri boş görünüyordu). Kenarlar bilinmiyorsa şekil yok.
    function gecersizSekil(t0, t1) {
        if (!sayi(t0) || !sayi(t1) || !(t1 > t0)) return null;
        return { type: 'rect', xref: 'x', yref: 'paper', x0: t0, x1: t1, y0: 0, y1: 1,
                 fillcolor: 'rgba(125,151,165,0.10)', line: { width: 0 } };
    }

    // V307/UÇUŞ-GÖVDE (kalem 6): rijit koşunun ZORUNLU etiketi ve sayıları
    // (yanıtın rijit_karsilastirma bloğundan; sayı yoksa adıyla söylenir).
    function referansMetni(rk) {
        const bas = T('panel.calkanti.sd.referansEtiket',
            'Slosh-free reference run — not a performance estimate of the sloshing vehicle; it shows neither a safe flight nor a conservative bound:');
        if (!rk) return bas + ' ' + T('panel.calkanti.sd.referansYok', 'not available.');
        const apo = sayi(rk.apogee)
            ? TF('panel.calkanti.sd.referansApoje', { apo: n(rk.apogee, 1) }, 'apogee {apo} m')
            : T('panel.calkanti.sd.referansApojeYok', 'apogee not reached');
        const alfa = sayi(rk.max_alpha_deg)
            ? TF('panel.calkanti.sd.referansAlfa', { alfa: n(rk.max_alpha_deg, 3) }, 'largest angle of attack {alfa}°')
            : '';
        return bas + ' ' + apo + (alfa ? ', ' + alfa : '') + '.';
    }

    // 6-DOF panelinin kendi zaman grafikleri (irtifa, hücum açısı) ve
    // rozetleri bağlaşık koşudandır: sınır aşıldıysa sonrası işaretlenir.
    // V307/UÇUŞ-GÖVDE (yayın kapısı 6, "iki tanım yan yana"): 6-DOF
    // rozetindeki uçuş hükmü bağlaşık uçuşun statik marjı ve hücum açısıdır;
    // çalkantı hükmü yanma boyunca donmuş katsayılı doğrusal taramanın
    // bulgusudur. Tarama kararsızlık bulduysa (örnek hibrit motorda ölçüldü:
    // rozet "KARARLI", alt bölüm "ÇALKANTI KAYNAKLI KARARSIZLIK") fark ve
    // nedeni rozetin hemen üstünde yazılır; sayılar yanıttan.
    function hukumNotunuKoy(h) {
        const eski = document.getElementById('sd_clk_hukum_notu');
        if (eski) eski.remove();
        if (!h || (h.genel_hukum !== 'CALKANTI_KAYNAKLI_KARARSIZLIK'
                   && h.genel_hukum !== 'RIJIT_GOVDE_KARARSIZ')) return;
        // Doğrusal sınır aşıldıysa rozette uçuş hükmü yoktur (yayım kuralı);
        // o durumu kırmızı uyarı söyler, bu not konmaz.
        if (h.dogrusal_sinir && h.dogrusal_sinir.asildi) return;
        const rozet = document.getElementById('sd_badges');
        if (!rozet || !rozet.parentNode) return;
        const pen = (h.genel_hukum === 'RIJIT_GOVDE_KARARSIZ' ? h.rijit_pencereler : h.pencereler) || [];
        const araliklar = pen.filter(function (p) { return p && sayi(p.t1) && sayi(p.t2); })
            .map(function (p) { return n(p.t1, 2) + '–' + n(p.t2, 2) + ' s'; });
        if (!araliklar.length) return;
        const d = document.createElement('div');
        d.id = 'sd_clk_hukum_notu';
        d.style.cssText = 'border:1px solid var(--hd-amber, #ffbe46); border-radius:8px; padding:8px 12px; margin:6px 0; font-size:0.82rem;';
        d.textContent = TF('panel.calkanti.hk.anaNot', { hukum: hk('hukum', h.genel_hukum), pencere: araliklar.join(', ') },
            'Slosh scan: {hukum} — the frozen-coefficient linear scan over the burn found an instability window ({pencere}). The flight verdict in the badges below is a different check (static margin and angle of attack of this coupled flight); details in the Stability — slosh subsection.');
        rozet.parentNode.insertBefore(d, rozet);
    }

    function anaCiktiyiIsaretle(h, rk) {
        const ds = h && h.dogrusal_sinir;
        const eski = document.getElementById('sd_clk_gecersiz_uyari');
        if (eski) eski.remove();
        hukumNotunuKoy(h);
        if (!ds || !ds.asildi || !sayi(ds.t_ilk_asim_s)) return;
        const rozet = document.getElementById('sd_badges');
        if (rozet && rozet.parentNode) {
            const d = document.createElement('div');
            d.id = 'sd_clk_gecersiz_uyari';
            d.style.cssText = 'border:1px solid var(--hd-red, #ff5d73); border-radius:8px; padding:8px 12px; margin:6px 0; font-size:0.82rem;';
            d.textContent = TF('panel.calkanti.hk.anaUyari', { t: n(ds.t_ilk_asim_s, 3) },
                'The coupled model passed the linear validity limit at t = {t} s; the trajectory estimate after that time is invalid. The apogee, speed, angle of attack and drift of the coupled run are not reported.')
                + ' ' + referansMetni(rk);
            rozet.parentNode.insertBefore(d, rozet);
        }
        if (typeof Plotly === 'undefined') return;
        ['sd_plot_alt', 'sd_plot_alpha'].forEach(function (id) {
            const g = document.getElementById(id);
            if (!g || !g.layout) return;
            const yeni = gecersizSekil(ds.t_ilk_asim_s, seriSonu(g.data));
            if (!yeni) return;
            const sekil = (g.layout.shapes || []).concat([yeni]);
            const not = (g.layout.annotations || []).concat([{ x: ds.t_ilk_asim_s, xref: 'x', y: 1, yref: 'paper',
                xanchor: 'left', yanchor: 'bottom', showarrow: false, font: { size: 12 },
                text: T('panel.calkanti.hk.gecersizKisa', 'linear model not valid beyond') }]);
            try { Plotly.relayout(g, { shapes: sekil, annotations: not }); } catch (e) { /* grafik yok */ }
        });
    }

    function sixdofCiz(data) {
        const el = document.getElementById('sd_calkanti_sonuc');
        if (!el) return;
        const u = U();
        if (u && u.purgePlots) u.purgePlots(el);
        el.innerHTML = '';
        const eskiUyari = document.getElementById('sd_clk_gecersiz_uyari');
        if (eskiUyari) eskiUyari.remove();
        const eskiNot = document.getElementById('sd_clk_hukum_notu');
        if (eskiNot) eskiNot.remove();
        sd.veri = data || null;
        const c = data && data.calkanti;
        const mt = motorTuru();
        if (!c) {
            if ((mt === 'liquid' || mt === 'hybrid') && data) {
                el.innerHTML = '<div style="font-size:0.82rem; margin:6px 0;">'
                    + esc(T('panel.calkanti.sd.yerYok', 'Tank location not entered; slosh is not coupled to the 6-DOF (no position is assumed).')) + '</div>';
            }
            return;
        }
        let html = '<h4 style="margin:10px 0 4px;">' + esc(T('panel.calkanti.sd.baslik', 'Stability — slosh subsection')) + '</h4>'
            + '<div style="font-size:0.8rem; color:var(--hd-orange, #ff8c33); margin:2px 0 6px;">'
            + esc(T('panel.calkanti.sd.kunye', 'Passive vehicle: the TVC/autopilot control loop is not modelled; for a guided vehicle this coupling is the main risk, and the hand-off table is meant for the vehicle team\'s GNC tool.')) + '</div>';
        const durumKey = {
            BAGLANDI: ['panel.calkanti.sd.durum.BAGLANDI', 'All tanks coupled to the 6-DOF.'],
            KISMI: ['panel.calkanti.sd.durum.KISMI', 'Some tanks coupled; the others are listed with their reasons.'],
            BAGLANMADI: ['panel.calkanti.sd.durum.BAGLANMADI', 'No tank coupled; the flight above is the rigid one.'],
            UYGULANMAZ: ['panel.calkanti.sd.durum.UYGULANMAZ', 'There is no liquid propellant in a solid motor; slosh does not apply.'],
        }[c.durum];
        if (durumKey) html += '<div style="font-size:0.84rem; margin:4px 0;">' + esc(T(durumKey[0], durumKey[1])) + '</div>';
        // Hüküm (ÇALKANTI-KARARLILIK sözleşmesi); uç yalnız sözleşmeli
        // çıktıyı yayımlar, yoksa hüküm alanı hiç çizilmez.
        const h = c.slosh_stability || null;
        if (h) html += hukumHtml(h);
        const asildi = !!(h && h.dogrusal_sinir && h.dogrusal_sinir.asildi);
        const rows = [];
        (c.tanklar || []).forEach(function (t) {
            const bagli = t.durum === 'BAGLANDI';
            let v = esc(bagli ? T('panel.calkanti.sd.tankBagli', 'coupled') : T('panel.calkanti.sd.tankBaglanmadi', 'not coupled'));
            if (bagli && sayi(t.x_tank_taban_m)) {
                v += ' — ' + esc(TF('panel.calkanti.sd.tankYer', { x: n(t.x_tank_taban_m, 3) }, 'tank bottom at x = {x} m from the nose'));
            }
            if (sayi(t.yuklenen_sivi_kg)) {
                v += ' — ' + esc(TF('panel.calkanti.sd.tankKutle', { m: n(t.yuklenen_sivi_kg, 3) }, 'loaded liquid {m} kg'));
            }
            rows.push([esc(tankAdi(t.tank_id)), v]);
        });
        if (rows.length) html += u.kvTable(rows);
        (c.tanklar || []).forEach(function (t) {
            const kod = (t.sebep || []).concat(t.beyan || []);
            const ucus = (c.tank_durum_kodlari || {})[t.tank_id] || [];
            ucus.forEach(function (k) { if (kod.indexOf(k) < 0) kod.push(k); });
            html += kodListesi(TF('panel.calkanti.sd.tankKodlar', { tank: tankAdi(t.tank_id) }, '{tank}: reasons and declarations'),
                               kod, t.durum === 'BAGLANDI' ? 'dim' : 'warn');
        });
        if (c.kutle_denetimi && typeof c.kutle_denetimi.tutarli === 'boolean') {
            html += '<div style="font-size:0.8rem; margin:4px 0;">' + esc(c.kutle_denetimi.tutarli
                ? T('panel.calkanti.sd.kutleTutarli', 'Tank masses close with the flight mass budget (loaded, consumed, remaining).')
                : T('panel.calkanti.sd.kutleTutarsiz', 'Tank masses do NOT close with the flight mass budget; the tanks are not coupled.')) + '</div>';
        }
        const rk = c.rijit_karsilastirma;
        const s = data.summary || {};
        if (rk) {
            // V307/UÇUŞ-GÖVDE (kalem 6): sınır aşılmadıysa yayımlanan sayı
            // bağlaşık koşudur, rijit koşu "çalkantısız karşılaştırma";
            // aşıldıysa bağlaşık sayı YOKTUR (yanıtta null), rijit koşu
            // referans etiketiyle durur.
            if (asildi) {
                html += u.kvTable([
                    [esc(T('panel.calkanti.sd.bagliKosu', 'Coupled run (with slosh): apogee, speed, angle of attack, drift')),
                        esc(TF('panel.calkanti.sd.bagliYayimlanmadi', { t: n(h.dogrusal_sinir.t_ilk_asim_s, 3) },
                            'not reported: the coupled model passed the linear validity limit at t = {t} s and the trajectory estimate after that time is invalid'))],
                ]) + '<div style="font-size:0.8rem; margin:4px 0;">' + esc(referansMetni(rk)) + '</div>';
            } else {
                html += u.kvTable([
                    [esc(T('panel.calkanti.sd.apoje', 'Apogee: coupled run (published) / slosh-free comparison')),
                        n(s.apogee, 1) + ' m / ' + n(rk.apogee, 1) + ' m'],
                    [esc(T('panel.calkanti.sd.maxAlfa', 'Max angle of attack: coupled run (published) / slosh-free comparison')),
                        n(s.max_alpha_deg, 3) + '° / ' + n(rk.max_alpha_deg, 3) + '°'],
                ]);
            }
        }
        const ust = document.createElement('div');
        ust.innerHTML = html;
        el.appendChild(ust);
        if (h) taramaGrafigi(el, h);
        anaCiktiyiIsaretle(h, rk);
        const z = c.zaman;
        if (!z || typeof Plotly === 'undefined' || !Array.isArray(z.time_s) || !z.tanklar || !z.tanklar.length) {
            if (c.durum === 'BAGLANDI' || c.durum === 'KISMI') {
                const yok = document.createElement('div');
                yok.style.cssText = 'font-size:0.8rem;';
                yok.textContent = T('panel.calkanti.sd.zamanYok', 'The time-domain slosh series was not produced; no plot is drawn.');
                el.appendChild(yok);
            }
            return;
        }
        const renk = ['#00e5ff', tokenRengi('var(--hd-amber-source, #ffb347)')];
        const t = z.time_s;
        const ekle = function (id) { const d = document.createElement('div'); d.id = id; el.appendChild(d); return d; };
        const maske = z.dogrusal_gecerli;
        const t0 = (asildi && sayi(h.dogrusal_sinir.t_ilk_asim_s)) ? h.dogrusal_sinir.t_ilk_asim_s : null;
        const izler = function (alan, donustur) {
            return maskeliIzler(z.tanklar.map(function (k, i) {
                return { x: t, y: donustur ? donustur(k) : k[alan], name: tankAdi(k.tank_id), type: 'scatter', mode: 'lines',
                         line: { color: renk[i % renk.length], width: 2 } };
            }), maske);
        };
        sdCizgi(ekle('sd_clk_aci'), izler('aci_deg'), T('panel.calkanti.sd.chAci', 'Slosh angle |η|/L1'),
            T('panel.calkanti.sd.axAci', 'Slosh angle (°)'), null, t0);
        const genlik = izler('ceper_genlik_orani');
        if (sayi(z.genlik_dogrusal_sinir_orani)) {
            genlik.push({ x: [t[0], t[t.length - 1]], y: [z.genlik_dogrusal_sinir_orani, z.genlik_dogrusal_sinir_orani],
                          name: TF('panel.calkanti.sd.trSinir', { s: n(z.genlik_dogrusal_sinir_orani, 1) },
                                   'linear-theory limit η/R = {s} (Dodge 2000 p. 33)'),
                          type: 'scatter', mode: 'lines', line: { color: tokenRengi('var(--hd-red, #ff5d73)'), width: 1.5, dash: 'dash' } });
        }
        sdCizgi(ekle('sd_clk_genlik'), genlik, T('panel.calkanti.sd.chGenlik', 'Wall wave amplitude η_wall/R'),
            T('panel.calkanti.sd.axGenlik', 'η_wall/R (-)'), null, t0);
        const buyukluk = function (a, b) {
            return function (k) {
                return k[a].map(function (v, j) {
                    const w = k[b][j];
                    return (sayi(v) && sayi(w)) ? Math.hypot(v, w) : null;
                });
            };
        };
        sdCizgi(ekle('sd_clk_kuvvet'), izler(null, buyukluk('kuvvet_y_N', 'kuvvet_z_N')),
            T('panel.calkanti.sd.chKuvvet', 'Lateral slosh force on the body |F|'), T('panel.calkanti.sd.axKuvvet', '|F| (N)'), null, t0);
        sdCizgi(ekle('sd_clk_moment'), izler(null, buyukluk('moment_y_Nm', 'moment_z_Nm')),
            T('panel.calkanti.sd.chMoment', 'Slosh pitch/yaw moment on the body |M|'), T('panel.calkanti.sd.axMoment', '|M| (N·m)'), null, t0);
        sdCizgi(ekle('sd_clk_tutum'), maskeliIzler([
            { x: t, y: z.delta_theta_deg, name: T('panel.calkanti.sd.trDtheta', 'Δθ attitude, coupled − rigid'),
              type: 'scatter', mode: 'lines', line: { color: '#00e5ff', width: 2 } },
            { x: t, y: z.delta_alpha_deg, name: T('panel.calkanti.sd.trDalfa', 'Δα angle of attack, coupled − rigid'),
              type: 'scatter', mode: 'lines', line: { color: '#c792ea', width: 2, dash: 'dot' } },
        ], maske), T('panel.calkanti.sd.chTutum', 'Effect on attitude (coupled − rigid run)'), T('panel.calkanti.sd.axDerece', 'Angle (°)'), null, t0);
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(el);
    }

    if (window.I18N && window.I18N.onChange) window.I18N.onChange(function () {
        // 6-DOF panelinin kendi yeniden çizimi (tazele) BU dinleyiciden sonra
        // kaydolur; işaretler onun grafiklerine çizim bittikten sonra konur.
        setTimeout(function () {
            try { sdDurumYaz(); if (sd.veri) sixdofCiz(sd.veri); } catch (e) { /* bölüm yok */ }
        }, 0);
    });

    window.HRMACalkanti = {
        mount: mount,
        mountSolid: mountSolid,
        motorDegisti: motorDegisti,
        sixdofForm: sixdofForm,
        sixdofBlok: sixdofBlok,
        sixdofCiz: sixdofCiz,
        sixdofTemizle: sixdofTemizle,
        // V307/KÜÇÜKLER (kalem 1): kod → metin tabloları kamu adıyla; Fırlatma
        // Sahası aynı tabloları okur (ikinci kopya yok). Eskiden alt çizgili
        // test kancası adlarıyla (`_HK`, `_kodMetni`) okunuyordu.
        HK: HK,
        kodMetni: kodMetni,
        _maskeliIzler: maskeliIzler,
        _gecersizSekil: gecersizSekil,
        _seriSonu: seriSonu,
        _hukumNotunuKoy: hukumNotunuKoy,
        _hukumHtml: hukumHtml,
        _istekGovdesi: istekGovdesi,
        _geoMetni: geoMetni,
        _KOD: KOD,
        _GEO: GEO,
        _durumlar: durumlar,
        _ciz: ciz,
    };
})();
