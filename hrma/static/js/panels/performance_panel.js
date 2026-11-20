/* ====================================================================
   HRMA Analiz Güvertesi — Gelişmiş Performans Paneli
   --------------------------------------------------------------------
   POST /api/advanced-performance-analysis sonuçlarını çizer.
   Endpoint çağrı başına TEK figür üretir (analysis_type seçicili):
   - 3d_surface  : Pc – O/F – Isp yüzeyi (kimyasal denge çözücüsü)
   - nozzle_mach : Mach–alan oranı konturu (NACA Rapor 1135 / Anderson,
                   "Modern Compressible Flow" — nozzle_flow_1d.py:12-26)
   - heat_flux   : cidar ısı akısı şelalesi (Bartz 1957; NASA SP-8124
                   "Liquid Rocket Engine Self-Cooled Combustion Chambers")
   DENETİM DÜZELTMESİ (2026-08-02, C2/C3): bu blok Mach–alan konturunun
   kaynağı olarak NASA-STD-5012 yazıyordu. O belgenin gerçek adı "Strength
   and Life Assessment Requirements for Liquid-Fueled Space Propulsion
   System Engines" (Rev. B, 2016) — bir mukavemet/ömür standardı; içinde
   gaz dinamiği bağıntısı yok. SP-8124 de "Thermal Design Criteria" değil.
   Doğrulanmış başlıklar: docs/STANDART_ATIFLARI.md.
   Dock'un kendi POST'u analysis_type göndermez → backend varsayılanı
   3d_surface döner; kalan iki figür render içinde ayrıca çekilir.
   Yanıt şeması (test_client ile doğrulandı, 2026-07-14):
     { status:'success', plot_data:'<JSON string {data,layout}>',
       analysis_info:{ title, reference, description } }
   Koyu tema plotly_dark.js sarmalayıcısından merkezi gelir.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu (i18n yoksa İngilizce yedek)

    const ENDPOINT = '/api/advanced-performance-analysis';

    // Ana POST (dock) → 3d_surface; bunlar render içinde ek olarak çekilir
    const EXTRA_FIGURES = [
        ['nozzle_mach', 'panel.performance.figMach', 'Nozzle Mach–Area Ratio Contour'],
        ['heat_flux', 'panel.performance.figHeat', 'Wall Heat Flux Waterfall'],
    ];

    // Motorun itici kimliği (fromResults'ta yakalanır, her istekte eklenir).
    // Form alanı DEĞİL: kullanıcı elle giremez, dolayısıyla motorla çelişemez.
    let sonIticiler = { fuel_type: null, oxidizer_type: null };

    // ------------------------------------------------------------------
    // V307/GÜVERTE-ORTAM — SIVI MOTORUN TASARIM ORTAMI (güverte panellerinin
    // TEK okuyucusu: PERFORMANS, KARŞILAŞTIRMA, BELİRSİZLİK)
    // ------------------------------------------------------------------
    // 3.0.7'de sıvı motorun tasarım ortamı girdidir (deniz seviyesi /
    // irtifa / basınç / vakum; çözücü `design_ambient` bloğunda beyan eder).
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V307/guverte-ortam/olcum/ortam_once.json):
    // vakum tasarımında güverte panelleri ortam söylemeden sayı basıyordu —
    // KARŞILAŞTIRMA'da deniz seviyesinde ayrılan vakum motorunun Isp'si
    // (327,07 s, vakum) deniz seviyesi Isp'leriyle (254,79 s) aynı başlık
    // altında sıralanıp "BEST ISP" seçiliyordu; PERFORMANS'ın Temel Isp
    // alanı vakum Isp'siyle doluyor, ortamı yazmıyordu.
    //
    // Tanım yanıtın KENDİ beyanından okunur, hiçbir sayı türetilmez:
    //   is_sea_level !== false      -> null (deniz seviyesi: etiket yok,
    //                                  ekran bugünküyle aynı)
    //   mode 'vacuum' / basınç 0    -> vakum
    //   irtifa (altitude_m) varsa   -> "{h} m tasarım irtifası ({p} bar)"
    //   yoksa basınç                -> "{p} bar tasarım ortamı"
    // Blok sıvı ve hibrit motorundur (`mode` alanı yalnız bu iki bloğda
    // var; V307/HİBRİT-ORTAM: hibrit `design_ambient` bloğu `mode`
    // 'sea_level' / 'pressure' / 'vacuum' ile aynı okuyucudan geçer). Katının
    // bloğu test ortamını anlatır ve paneller katıda deniz seviyesi Isp'sini
    // okur — bu okuyucu katıya uygulanmaz.
    // `key` iki tasarımın AYNI ortamda olup olmadığının kimliğidir (yanıtın
    // basınç sayısı; irtifası aynı iki tasarım aynı ISA basıncını taşır).
    const ORTAM_ANAHTARLARI = {
        vacuum: ['panel.ambient.vacuum', 'vacuum'],
        altitudeP: ['panel.ambient.altitudeP', '{h} m design altitude ({p} bar)'],
        altitude: ['panel.ambient.altitude', '{h} m design altitude'],
        pressure: ['panel.ambient.pressure', '{p} bar design ambient'],
    };

    function ortamSonlu(v) {
        return (typeof v === 'number' && isFinite(v)) ? v : null;
    }

    function ortamTanimi(da) {
        if (!da || typeof da !== 'object' || da.is_sea_level !== false
                || typeof da.mode !== 'string') {
            return null;
        }
        const p = ortamSonlu(da.pressure_bar);
        const h = ortamSonlu(da.altitude_m);
        if (da.mode === 'vacuum' || p === 0) {
            return { kind: 'vacuum', key: 'p:0', p: 0, h: null };
        }
        if (p === null && h === null) {
            // Ortam beyan edilmiş ama sayısı yok: tanım yok sayılmaz, adıyla
            // "beyan edilmedi" kimliği taşır (hiçbir ortamla eşleşmez).
            return { kind: 'undeclared', key: 'undeclared', p: null, h: null };
        }
        return {
            kind: (h !== null) ? (p !== null ? 'altitudeP' : 'altitude') : 'pressure',
            key: (p !== null) ? ('p:' + p) : ('h:' + h),
            p: p, h: h,
        };
    }

    // BELİRSİZLİK paneli için: isteğe giden form alanlarından aynı tanım
    // (fabrikanın kurduğu motor bu alanlarla kurulur; deniz seviyesinde sayfa
    // bu alanları HİÇ göndermez).
    function ortamTanimiGirdiden(g) {
        if (!g || typeof g !== 'object') return null;
        const kip = g.design_ambient_mode;
        if (kip === 'vacuum') {
            return ortamTanimi({ is_sea_level: false, mode: 'vacuum', pressure_bar: 0 });
        }
        if (kip === 'altitude') {
            return ortamTanimi({ is_sea_level: false, mode: 'altitude',
                                 altitude_m: ortamSonlu(g.design_ambient_altitude_m) });
        }
        if (kip === 'pressure') {
            return ortamTanimi({ is_sea_level: false, mode: 'pressure',
                                 pressure_bar: ortamSonlu(g.design_ambient_pressure_bar) });
        }
        // V307/HİBRİT-ORTAM: hibrit gövdesi tasarım ortamını
        // `atmospheric_pressure` (bar) ile taşır (sıvı/katı gövdelerinde bu
        // ad yok). ISA deniz seviyesi (1,01325 bar) etiketsiz; alan gövdede
        // okunamıyorsa tanım "beyan edilmedi" kimliği taşır (hiçbir ortamla
        // eşleşmez; sayı varsayılmaz).
        if (kip === undefined && g.atmospheric_pressure !== undefined) {
            const pHib = (typeof g.atmospheric_pressure === 'number')
                ? ortamSonlu(g.atmospheric_pressure) : null;
            if (pHib === 1.01325) return null;
            return ortamTanimi({ is_sea_level: false,
                                 mode: pHib === 0 ? 'vacuum' : 'pressure',
                                 pressure_bar: pHib });
        }
        return null;
    }

    // Etiketin anahtarı + parametreleri. Basınç dört basamakla (sıvı
    // sayfasının tasarım ortamı satırıyla aynı: liquid.html
    // liqDesignAmbientNote `sayi(da.pressure_bar, 4)`); ayraç tf'de.
    function ortamEtiketParcalari(t) {
        if (!t) return null;
        if (t.kind === 'undeclared') {
            return { key: 'panel.ambient.undeclared',
                     fb: 'design ambient not declared by the result', params: null };
        }
        const k = ORTAM_ANAHTARLARI[t.kind];
        const params = (t.kind === 'vacuum') ? null : {};
        if (params && t.h !== null) params.h = Math.round(t.h);
        if (params && t.p !== null) params.p = t.p.toFixed(4);
        return { key: k[0], fb: k[1], params: params };
    }

    function ortamEtiketMetni(t) {
        const e = ortamEtiketParcalari(t);
        if (!e) return '';
        return e.params ? U.tf(e.key, e.params, e.fb) : T(e.key, e.fb);
    }

    // Dil değişince kendiliğinden çevrilen düğüm (data-i18n-params; tf).
    function ortamEtiketHtml(t) {
        const e = ortamEtiketParcalari(t);
        if (!e) return '';
        return '<span data-isp-ambient="' + U.esc(t.kind) + '" data-i18n="'
            + U.esc(e.key) + '"'
            + (e.params ? ' data-i18n-params="' + U.esc(JSON.stringify(e.params)) + '"' : '')
            + '>' + U.esc(ortamEtiketMetni(t)) + '</span>';
    }

    // V307/KÜÇÜKLER-2 (kalem 3, 4): tanım -> uçların ortam kaydı
    // ({mode, pressure_bar, altitude_m}; app.py ``_tasarim_ortami_kaydi_oku``).
    // null = deniz seviyesi (okunan Isp deniz seviyesi Isp'sidir); sayı
    // türetilmez, tanımın sayısı aynen geçer. Sunucu etiketi bu panelin
    // `panel.ambient.*` metniyle aynı ifadeyi yazar.
    function ortamKaydi(t) {
        if (!t) return { mode: 'sea_level' };
        if (t.kind === 'vacuum') return { mode: 'vacuum' };
        if (t.kind === 'undeclared') return { mode: 'undeclared' };
        if (t.kind === 'altitudeP' || t.kind === 'altitude') {
            return { mode: 'altitude', altitude_m: t.h, pressure_bar: t.p };
        }
        return { mode: 'pressure', pressure_bar: t.p };
    }

    window.HRMAIspAmbient = {
        describe: ortamTanimi,
        describeInputs: ortamTanimiGirdiden,
        labelText: ortamEtiketMetni,
        labelHtml: ortamEtiketHtml,
        record: ortamKaydi,
    };

    // PERFORMANS: Temel Isp alanına önerilen sayı motorun tasarım ortamı
    // Isp'sidir (sıvıda deniz seviyesi dışındaki tasarımda `specific_impulse`
    // = `isp_design_ambient`). Ortam deniz seviyesi değilse bölümün içinde,
    // durum satırının önünde GÖRÜNÜR bir not durur (ipucunda saklanmaz);
    // deniz seviyesinde not yoktur (ekran bugünküyle aynı).
    const PERF_ORTAM_NOT_ID = 'ad_perf_isp_ambient';
    let tabanIspOrtami = null;
    //: V307/KÜÇÜKLER-2 (kalem 4): motorun önerdiği Temel Isp (tohum). Alan
    //: hâlâ bu sayıyı taşıyorsa ortam kaydı isteğe girer; kullanıcı sayıyı
    //: değiştirdiyse ortamı bilinmez, kayıt GİRMEZ (ortam varsayılmaz).
    let tabanIspTohumu = null;
    // V307/ONARIM-İTKİ-A (M7-ITKI-7): motorun tasarım ortamı kaydı (Temel
    // Isp tohumundan BAĞIMSIZ). Mach konturu lülenin ortamıdır; Temel Isp
    // alanı elle değişse de motorun ortamı değişmez. Blok `mode` taşımıyorsa
    // (katı) null: kayıt gönderilmez, uç bugünkü gibi davranır.
    let motorOrtamKaydi = null;

    function tabanIspTohumdaMi(v) {
        if (tabanIspTohumu === null || typeof v !== 'number') return false;
        if (v === tabanIspTohumu) return true;
        // Güverte öneriyi alana kendi anlamlı basamağıyla yazar
        // (analysis_dock dockSigFig; sayı `AnalysisDock.ui.SIGFIG`).
        const ui = window.AnalysisDock && window.AnalysisDock.ui;
        const d = ui && ui.SIGFIG;
        return (typeof d === 'number' && d > 0)
            ? v === Number(tabanIspTohumu.toPrecision(d)) : false;
    }

    function tabanIspNotunuYaz() {
        if (typeof document === 'undefined' || !document.getElementById) return;
        const sec = document.getElementById('ad_sec_performance');
        let not = document.getElementById(PERF_ORTAM_NOT_ID);
        if (!tabanIspOrtami) {
            if (not && not.parentNode && typeof not.parentNode.removeChild === 'function'
                    && not.getAttribute && not.getAttribute('data-perf-isp-ambient')) {
                not.parentNode.removeChild(not);
            } else if (not) {
                not.innerHTML = '';
                if (not.style) not.style.display = 'none';
            }
            return;
        }
        if (!sec) return;
        if (!not || !not.getAttribute || !not.getAttribute('data-perf-isp-ambient')) {
            not = document.createElement('p');
            not.id = PERF_ORTAM_NOT_ID;
            not.setAttribute('data-perf-isp-ambient', '1');
            not.style.cssText = 'font-size:0.74rem; margin:6px 0;'
                + ' color:var(--hd-orange, #ff8c33); white-space:normal;';
            const status = document.getElementById('ad_status_performance');
            if (status && status.parentNode === sec) sec.insertBefore(not, status);
            else sec.appendChild(not);
        }
        if (not.style) not.style.display = '';
        not.innerHTML = '<span data-i18n="panel.performance.baseIspAmbient">'
            + U.esc(T('panel.performance.baseIspAmbient',
                'Base Isp is filled with this motor\'s Isp at its design ambient, '
                + 'not at sea level:')) + '</span> <strong>'
            + ortamEtiketHtml(tabanIspOrtami) + '</strong>. '
            + '<span data-i18n="panel.performance.baseIspAmbientSurface">'
            + U.esc(T('panel.performance.baseIspAmbientSurface',
                'The 3D Isp surface is solved for sea-level expansion '
                + '(Pe = 1 bar); the figure states how it places this '
                + 'design-point Isp against that basis.')) + '</span>';
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(not);
    }

    // ------------------------------------------------------------------
    // Dock buildPayload aynası: POST gövdesi HER ZAMAN formdan okunur
    // (panel dock dosyasına dokunmadan aynı sözleşmeyi uygular)
    // ------------------------------------------------------------------
    function readFormPayload() {
        const payload = {};
        const sec = document.getElementById('ad_sec_performance');
        if (!sec) return payload;
        sec.querySelectorAll('[data-field]').forEach(function (el) {
            const key = el.getAttribute('data-field');
            if (el.tagName === 'SELECT') {
                payload[key] = el.value;
                return;
            }
            const v = parseFloat(el.value);
            if (Number.isFinite(v)) payload[key] = v;
        });
        // İtici kimliği (T18): bilinmiyorsa GÖNDERİLMEZ — uydurma bir çift
        // yollamaktansa uç kendi referans çiftine düşsün ve bunu beyan etsin.
        if (sonIticiler.fuel_type) payload.fuel_type = sonIticiler.fuel_type;
        if (sonIticiler.oxidizer_type) payload.oxidizer_type = sonIticiler.oxidizer_type;
        // V307/KÜÇÜKLER-2 (kalem 4): Temel Isp motorun tohumuysa onun tasarım
        // ortamı adıyla gider; yüzey künyesi "design ambient: …" der.
        if (tabanIspTohumdaMi(payload.base_isp)) {
            payload.design_ambient = ortamKaydi(tabanIspOrtami);
        }
        return payload;
    }

    // ------------------------------------------------------------------
    // Birim sözleşmesi (2026-07-19 Codex denetimi, bulgu 5)
    // ------------------------------------------------------------------
    // Üst seviye motor sonuçları tipe göre FARKLI birim kullanır:
    //   katı   : throat_diameter 47.93 -> MİLİMETRE
    //   sıvı   : chamber_length 97.96  -> MİLİMETRE, throat_diameter METRE
    //   hibrit : hepsi METRE
    // Panel hepsini SI sanıyordu: sıvıda kamara 1000 kat uzun, katıda boğaz
    // alanı 10^6 kat büyük gidiyordu. Tek doğruluk kaynağı normalize
    // `motor_geometry` bloğudur (her alan SI).
    //
    // ÖH D33-2 / arayuz-panel a1 · kalem OH-D32-01 (defter zinciri P7B1-06)
    // -------------------------------------------------------------------
    // BURADA İKİNCİ BİR BANT DURUYORDU: çap tavanı 1,0 m ve boy tavanı
    // 5,0 m elle yazılıydı, blok yoksa "değer tavanın üstündeyse değer
    // milimetredir" diye ÇIKARIM yapılıyordu. ÖLÇÜLDÜ (a1/once.json,
    // bölüm K1): bu iki sayı doğrulayıcının KENDİ kanonuyla ayrışıyordu —
    // motor_validation.DIAMETER_UNIT_INFERENCE_MAX_M 5,0 m ve
    // LENGTH_UNIT_INFERENCE_MAX_M 20,0 m (ikisi de CANONICAL_LIMITS
    // tablosundan TÜRETİLİR, elle yazılmaz). Aradaki boşlukta kalan meşru
    // ölçüler panelde 1000 kat küçülüyordu:
    //
    //     girdi (kanonik bant içi)   panel okudu     sunucu okur
    //     chamber_diameter 1,5 m     0,0015 m        1,5 m
    //     chamber_length   6,0 m     0,006 m         6,0 m
    //     throat_diameter  1,2 m  -> alan 1,131e-6 m²  1,131 m² (10^6 kat)
    //
    // Bandı arayüze yayımlayan bir uç YOK (/api/limits benzeri uç
    // app-api-uc kulvarına devredildi — bkz. a1/rapor.md). Bandın ikinci
    // kopyası TAŞINMAZ ve sayı UYDURULMAZ; birim çözümü ürünün MEVCUT tek
    // kaynağına devredilir (aşağıdaki geoLength).
    // Canlı yolda kayıp yoktur: ÖLÇÜLDÜ (a1/once.json, K1) üç motor
    // tipinin /calculate ailesi de `motor_geometry` bloğunu
    // chamber_length / chamber_diameter / throat_diameter ile yayımlıyor.
    // Blok GELMEYEN yol da ölçüldü: ham `HybridRocketEngine.calculate()`
    // sonucu `motor_geometry` taşımaz (üst seviye metre) ve tamamen silmek
    // tests/test_unit_contract.py::TestPerformancePanelUnits::
    // test_throat_area_and_chamber_length_are_physical[hybrid] bekçisini
    // kırıyordu — yani gerçek bir yeteneği düşürüyordu. Güvertenin
    // ölçülmüş birim tablosuna devir hem kusuru hem o kaybı kapatır.

    //: Bu turda birimi ÇÖZÜLEMEYEN alan adları — sessiz yedek yerine ADLI
    //: yokluk. Test yüzeyi bunu `_unresolvedGeometry()` ile okur.
    let birimiCozulemeyenAlanlar = [];

    // Birim çözümü İKİ TEK-KAYNAKTAN gelir, panelden ASLA:
    //   1) normalize `motor_geometry` bloğu (her alan SI — uç garanti eder),
    //   2) güvertenin MERKEZİ birim sözleşmesi
    //      (`analysis_dock.js::readLengthM`, motor tipine göre ÖLÇÜLMÜŞ
    //      `LENGTH_UNITS` tablosu — hibrit 'm', katı 'mm', sıvıda alan alan).
    // İkisi de konuşmuyorsa alan ÖNERİSİZ kalır ve adı beyan edilir.
    // Büyüklükten çıkarım (eski `siLength`) YOK: bir sayının kaç olduğu
    // birimini söylemez.
    function geoLength(m, geo, key, r) {
        if (geo && Number.isFinite(geo[key]) && geo[key] > 0) return geo[key];
        if (U && typeof U.readLengthM === 'function') {
            const v = U.readLengthM(r, key);
            if (typeof v === 'number' && Number.isFinite(v) && v > 0) return v;
        }
        if (m && m[key] !== undefined && m[key] !== null
                && birimiCozulemeyenAlanlar.indexOf(key) < 0) {
            birimiCozulemeyenAlanlar.push(key);
        }
        return null;
    }

    // İlk sonlu pozitif değer (üretici/tüketici anahtar adı farkları için)
    //: V307/GRAFİK-BİRİM (kalem 2) — molekül ağırlığının okunduğu yollar,
    //: thermal_panel.js ``MW_YOLLARI`` ile AYNI sıra (bekçi:
    //: tests/test_v307_grafik_birim.py): önce motorun kendi Bartz gaz
    //: çifti (katı), sonra üst düzey ``molecular_weight`` (hibrit, sıvı),
    //: sonra termokimya kaydı. Hiçbiri yoksa öneri yok, alan boş kalır.
    const MW_YOLLARI = ['heat_transfer_analysis.bartz_gas_properties.molecular_weight',
                        'molecular_weight', 'thermochemistry.molecular_weight'];

    function ilkYolSayisi(obj, yollar) {
        for (let i = 0; i < yollar.length; i++) {
            let v = obj;
            const parca = yollar[i].split('.');
            for (let j = 0; j < parca.length && v !== null && v !== undefined; j++) {
                v = (typeof v === 'object') ? v[parca[j]] : undefined;
            }
            if (typeof v === 'number' && Number.isFinite(v) && v > 0) return v;
        }
        return null;
    }

    function firstFinite(obj, keys) {
        for (let i = 0; i < keys.length; i++) {
            const v = Number(obj[keys[i]]);
            if (Number.isFinite(v)) return v;
        }
        return null;
    }

    // plot_data backend'den JSON *string* gelir (PlotlyJSONEncoder);
    // obje gelirse de tolere edilir. Geçersiz payload → null.
    function parseFigure(pd) {
        try {
            const fig = (typeof pd === 'string') ? JSON.parse(pd) : pd;
            if (fig && Array.isArray(fig.data)) return fig;
        } catch (e) { /* aşağıda null */ }
        return null;
    }

    // V307/ONARIM-İTKİ-A (M7-ITKI-7): kartın başlık/açıklaması sunucu
    // metnidir; grafik sözlüğünden (I18N.chartText) geçer — TR ekranda
    // "Nozzle Mach Distribution Analysis" İngilizce kalıyordu. Kaynak adı
    // (belge başlığı) özel addır, çevrilmez.
    function kartMetni(t) {
        if (!t) return '';
        return (window.I18N && typeof window.I18N.chartText === 'function')
            ? window.I18N.chartText(String(t)) : String(t);
    }

    function infoCard(info) {
        if (!info || (!info.title && !info.description)) return '';
        info = { title: kartMetni(info.title), reference: info.reference,
                 description: kartMetni(info.description) };
        return `<div style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
            border-left:3px solid var(--hd-cyan, #00e5ff);
            border-radius:var(--hd-radius-sm, 8px); padding:10px 14px; margin:8px 0;
            background:var(--hd-inset, rgba(6,14,26,0.85));">
            <strong style="color:var(--hd-ink-strong, #eaf7fb);">${info.title || ''}</strong>
            <div style="font-family:var(--hd-mono); font-size:0.7rem;
                 color:var(--hd-ink-dim, #7d97a5); margin:2px 0;">${info.reference || ''}</div>
            <p style="margin:6px 0 0; font-size:0.8rem;
               color:var(--hd-ink, #cfe8f2);">${info.description || ''}</p>
        </div>`;
    }

    // Bir figür bloğu: başlık + durum satırı + bilgi kartı alanı + grafik
    function figureBlock(root, heading) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '14px';
        wrap.innerHTML = U.sectionTitle(heading);
        const status = document.createElement('div');
        status.style.cssText = 'font-family:var(--hd-mono); font-size:0.78rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:4px 0;';
        const info = document.createElement('div');
        const plot = document.createElement('div');
        wrap.appendChild(status);
        wrap.appendChild(info);
        wrap.appendChild(plot);
        root.appendChild(wrap);
        return { wrap: wrap, status: status, info: info, plot: plot };
    }

    // Yanıtı bloğa çizer; başarıysa true
    function drawResponse(block, resp) {
        block.info.innerHTML = infoCard(resp && resp.analysis_info);
        const fig = parseFigure(resp && resp.plot_data);
        if (!fig) {
            block.status.textContent = T('common.badPayload',
                'Unexpected plot payload from backend.');
            return false;
        }
        if (typeof Plotly === 'undefined') {
            block.status.textContent = T('common.plotlyMissing',
                'Plotly is not loaded — chart skipped.');
            return false;
        }
        Plotly.newPlot(block.plot, fig.data, fig.layout || {},
            { responsive: true, displaylogo: false });
        block.status.textContent = '';
        return true;
    }

    // Ek figürleri (nozzle_mach / heat_flux) formdaki güncel değerlerle çek
    async function fetchExtraFigure(analysisType, headingKey, headingEn, root) {
        const block = figureBlock(root, T(headingKey, headingEn));
        block.status.textContent = T('common.loading', 'LOADING…');
        try {
            const payload = readFormPayload();
            payload.analysis_type = analysisType;
            // V307/ONARIM-İTKİ-A (M7-ITKI-7): Mach konturu motorun tasarım
            // ortamında çözülür (vakum tasarımı vakumda); kayıt yoksa uç
            // ortamı adıyla "varsayıldı" diye yazar.
            if (analysisType === 'nozzle_mach' && motorOrtamKaydi
                    && payload.ambient_pressure === undefined
                    && payload.ambient_pressure_bar === undefined) {
                payload.design_ambient = motorOrtamKaydi;
            }
            const resp = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (resp.status === 404 || resp.status === 501) {
                // Zarif düşüş: endpoint geçici yoksa panel kırılmaz
                block.status.textContent = T('common.backendUpdating',
                    'Backend updating — this figure will be available after the server reloads.');
                return;
            }
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                throw new Error((data && data.error) || ((window.HRMAReject && window.HRMAReject.yedek) ? window.HRMAReject.yedek(resp.status) : ('HTTP ' + resp.status)));
            }
            drawResponse(block, data);
        } catch (err) {
            block.status.textContent = U.tf('common.errorPrefix',
                { message: err.message }, 'ERROR: {message}');
        }
    }

    function render(data, root) {
        // 1) Dock'un kendi POST yanıtı — 3D performans yüzeyi
        const main = figureBlock(root, T('panel.performance.figSurface',
            '3D Performance Surface — Isp vs Chamber Pressure & O/F'));
        drawResponse(main, data);

        // 2) Kalan iki hazır figür ayrı çağrılarla (paralel) gelir
        EXTRA_FIGURES.forEach(function (f) {
            fetchExtraFigure(f[0], f[1], f[2], root);
        });
    }

    // ------------------------------------------------------------------
    // ÖH D37 A1a pdf-grafik-step · CW-SU6 — KATIDA O/F HARİTASI İSTENMEZ
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (``docs/scofield/raw/OH/A1a/pdf-grafik-step/a1/once.json``
    // K4): panel üç motor tipine de kaydoluyordu ve güvertenin POST'u
    // `analysis_type` göndermediği için uç her Çalıştır'da 3B yüzeyi
    // (Isp – Pc – O/F) döndürüyordu — katı sayfasında da. Önceden
    // karıştırılmış katı itici için O/F bir tasarım değişkeni DEĞİLDİR;
    // katının iticisi yakıt/oksitleyici çifti de taşımadığından yüzey uç
    // tarafında referans çiftine düşüyordu. Sunucu motor tipini göremez
    // (`app.py` `engine_data` gövdesinde `motor_type` yok) → karar istemcide:
    //   * hibrit/sıvı: 'performance' kaydı AYNEN (yüzey + iki ek figür);
    //   * katı: ayrı kayıt; güvertenin POST'u `analysis_type` seçicisiyle
    //     gider (Mach konturu / ısı akısı), yüzey HİÇ istenmez ve yerinde
    //     gri + neden durur. Yalnız yüzeyi besleyen iki alan (O/F, taban
    //     Isp — `app.py` 3d_surface `engine_data`) katı formunda yok.
    const SURFACE_ONLY_FIELDS = ['optimal_of_ratio', 'base_isp'];
    const SOLID_OF_NA_EN = 'The 3D performance surface (Isp vs chamber '
        + 'pressure and O/F) is not drawn for a solid motor: O/F is not a '
        + 'design variable of a premixed solid propellant — its oxidizer-to-'
        + 'fuel ratio is fixed by the propellant formulation. The figure was '
        + 'not requested.';
    // Seçici seçenekleri güvertenin biçiminde: [değer, etiket, etiketAnahtarı]
    const SOLID_FIGURES = EXTRA_FIGURES.map(function (f) {
        return [f[0], f[2], f[1]];
    });

    function selectedSolidFigure() {
        const sec = document.getElementById('ad_sec_performance_solid');
        const el = sec && sec.querySelector
            ? sec.querySelector('[data-field="analysis_type"]') : null;
        const v = el ? el.value : null;
        for (let i = 0; i < SOLID_FIGURES.length; i++) {
            if (SOLID_FIGURES[i][0] === v) return SOLID_FIGURES[i];
        }
        return null;
    }

    function renderSolid(data, root) {
        // 1) Yüzeyin yerinde gri + neden — figür istenmedi, çizilmez.
        const na = document.createElement('div');
        na.setAttribute('data-perf-na', 'of_surface');
        na.style.cssText = 'border:1px dashed var(--hd-line, rgba(125,151,165,0.45));'
            + ' border-radius:var(--hd-radius-sm, 8px); padding:10px 14px;'
            + ' margin:8px 0; color:var(--hd-ink-dim, #7d97a5); font-size:0.8rem;';
        na.innerHTML = U.sectionTitle(T('panel.performance.figSurface',
            '3D Performance Surface — Isp vs Chamber Pressure & O/F'));
        const neden = document.createElement('p');
        neden.style.margin = '6px 0 0';
        neden.textContent = T('panel.performance.solidOfNa', SOLID_OF_NA_EN);
        na.appendChild(neden);
        root.appendChild(na);
        // 2) Güvertenin POST'u seçilen figürü döndürdü.
        const secim = selectedSolidFigure();
        const baslik = secim ? T(secim[2], secim[1])
            : ((data && data.analysis_info && data.analysis_info.title)
               || T('panel.performance.titleSolid',
                    'Advanced Performance — Mach Contour, Heat Flux'));
        drawResponse(figureBlock(root, baslik), data);
    }

    // V307/SEKME-GÜVERTE (NK3-H-7) — TOHUM YOKSA ANALİZ KOŞMAZ.
    // ÖLÇÜLDÜ (NK3-H, örnek hibrit: Hesapla → Yanma Süresi 0 → Hesapla
    // reddedildi → PERFORMANS → Analizi Çalıştır; kanıt
    // docs/scofield/raw/OH/V307/sekme-guverte/olcum_once_bayat.json): son hesap
    // başarısızken güverte önerilen alanları TANIM VARSAYILANINA döndürüyor
    // (OH-D37-S4, doğru) ama bu panelin tanım varsayılanları gizli bir motordu
    // (Pc 50 bar, O/F 3,5, Isp 300 s, ε 16, boğaz 0,001 m², oda Ø 0,1 m,
    // T_c 3000 K, γ 1,2, ṁ 1 kg/s) ve "Analizi Çalıştır" o motoru çözüp "akış
    // ayrılması" çiziyordu. Motordan gelen her büyüklüğün tanım değeri artık
    // BOŞTUR: tohum yoksa alan boş kalır, `required` alanlar boşsa güverte
    // isteği göndermez ve eksikleri adıyla söyler (dock.missingFields);
    // kullanıcı değerleri kendisi girerse koşar. İsteğe bağlı boş alan
    // gövdeye girmez (uç ve figür modülü onu adıyla "varsayıldı" listesine
    // yazar ya da hiç çizmez). Isı akısı figürünün iki referans düzlemi
    // (taban / kritik akı) motor büyüklüğü değildir ve kaynaksız sayıyla
    // ön doldurulmaz: boşsa çizilmez (app.py ``_APA_REQUIRED_ANY_OF``
    // künyesi: "sorulmamış bir referans çizgisi çizilmez").
    const PERF_FIELDS = [
            ['chamber_pressure', 'Chamber Pressure (bar)', '', 1, 'common.f.chamberPressureBar', 'panel.performance.help.chamber_pressure'],
            // V301/H-PANEL (NK-73): alan TASARIM noktasının O/F'sidir (yardım
            // metni ve tohum: motorun of_ratio'su) — etiket "Optimum" diyordu.
            // Alan kimliği (optimal_of_ratio) uç sözleşmesidir, değişmez.
            ['optimal_of_ratio', 'Design O/F Ratio', '', 0.1, 'panel.performance.f.designOf', 'panel.performance.help.optimal_of_ratio'],
            ['base_isp', 'Base Isp (s)', '', 5, 'common.f.baseIsp', 'panel.performance.help.base_isp'],
            ['expansion_ratio', 'Expansion Ratio', '', 0.5, 'common.f.expansionRatio', 'panel.performance.help.expansion_ratio'],
            ['throat_area', 'Throat Area (m²)', '', 0.0001, 'common.f.throatAreaM2', 'panel.performance.help.throat_area'],
            ['nozzle_length', 'Nozzle Length (m)', '', 0.01, 'common.f.nozzleLengthM', 'panel.performance.help.nozzle_length'],
            ['chamber_length', 'Chamber Length (m)', '', 0.01, 'common.f.chamberLengthM', 'panel.performance.help.chamber_length'],
            ['burn_time', 'Burn Time (s)', '', 0.5, 'common.f.burnTimeS', 'panel.performance.help.burn_time'], // OH-D37-S6: süre uydurulmaz — boşsa gövdeye girmez (safety_panel.js deseni)
            ['base_heat_flux', 'Base Heat Flux (W/m²)', '', 100000, 'common.f.baseHeatFlux', 'panel.performance.help.base_heat_flux'],
            ['critical_heat_flux', 'Critical Heat Flux (MW/m²)', '', 0.5, 'common.f.criticalHeatFlux', 'panel.performance.help.critical_heat_flux'],
            // Bartz ısı akısı çözücüsünün gaz hâli girdileri (bulgu 6): bunlar
            // gönderilmediğinde backend 3000 K / gamma 1.2 / 1 kg/s
            // varsayılanlarına düşüyor ve farklı itergaçlar aynı grafiği veriyordu.
            ['chamber_temperature', 'Chamber Temperature (K)', '', 50, 'common.f.chamberTemperatureK', 'panel.performance.help.chamber_temperature'],
            ['gamma', 'Gamma (frozen)', '', 0.01, 'common.f.gammaFrozen', 'panel.performance.help.gamma'],
            // V307/GRAFİK-BİRİM (kalem 2): MW alanı YOKTU — Mach / ısı akısı
            // figürleri motorun yayımladığı MW yerine beyanlı 24 g/mol
            // varsayımıyla çiziliyordu. İsteğe bağlı: boşsa gövdeye girmez,
            // figür varsayımını alt başlıkta adıyla yazar.
            ['molecular_weight', 'Molecular Weight (g/mol)', '', 0.5, 'common.f.molecularWeight', 'panel.performance.help.molecular_weight'],
            ['mdot_total', 'Total Mass Flow (kg/s)', '', 0.1, 'common.f.mdotTotal', 'panel.performance.help.mdot_total'],
            ['chamber_diameter', 'Chamber Diameter (m)', '', 0.01, 'common.f.chamberDiameterM', 'panel.performance.help.chamber_diameter'],
    ];

    //: NK3-H-7: motorun tanımladığı büyüklükler — boşsa istek GÖNDERİLMEZ
    //: (güverte `required` sözleşmesi; panelde olmayan ad yok sayılır, katı
    //: kaydında O/F ve taban Isp alanı yoktur).
    const PERF_REQUIRED = ['chamber_pressure', 'optimal_of_ratio', 'base_isp',
                           'expansion_ratio', 'throat_area', 'chamber_length',
                           'chamber_temperature', 'gamma', 'chamber_diameter'];

    // V307/ONARIM-İTKİ-A (M7-ITKI-8): motorun itici kimliği. ÖLÇÜLDÜ
    // (mühendis turu H4_perf): hibrit sonucu üst düzeyde `oxidizer_type`
    // taşımıyor (yalnız `fuel_type`); çözücünün kendi girdisi
    // `combustion_analysis.inputs` içinde. Sıra: üst düzey ad, sonra
    // çözücü girdisi. Bulunamazsa null: uç referans çifte düşer ve bunu
    // adıyla yazar (kimlik uydurulmaz).
    function iticiKimligi(m) {
        const ci = (m && m.combustion_analysis && typeof m.combustion_analysis === 'object'
                    && m.combustion_analysis.inputs
                    && typeof m.combustion_analysis.inputs === 'object')
            ? m.combustion_analysis.inputs : {};
        const ad = function (v) { return (typeof v === 'string' && v.trim()) ? v : null; };
        return {
            fuel_type: ad(m && m.fuel_type) || ad(m && m.fuel) || ad(ci.fuel_type),
            oxidizer_type: ad(m && m.oxidizer_type) || ad(m && m.oxidizer) || ad(ci.oxidizer_type),
        };
    }

    // V307/ONARIM-İTKİ-A (M7-ITKI-8): güvertenin İLK koşusu (Analizi
    // Çalıştır → 3B yüzey) gövdeyi güvertenin kendi `buildPayload`ıyla
    // kurar; panelin `readFormPayload` eklerini (itici kimliği, Temel Isp'nin
    // tasarım ortamı) taşımıyordu ve yüzey RP-1/LOX motorunda bile N2O/HTPB
    // referans çiftiyle çözülüyordu. Güvertenin form dışı bağlam kanalı
    // (`contextFromResults`; form alanını ezmez) aynı ekleri verir.
    function baglamSonuctan(r, govde) {
        const m = (r && r.motor) || r || {};
        sonIticiler = iticiKimligi(m);
        const b = {};
        if (sonIticiler.fuel_type) b.fuel_type = sonIticiler.fuel_type;
        if (sonIticiler.oxidizer_type) b.oxidizer_type = sonIticiler.oxidizer_type;
        // readFormPayload ile aynı kural: Temel Isp motorun tohumuysa
        // tasarım ortamı adıyla gider (güvertenin kurduğu gövdeden okunur).
        const g = (govde && typeof govde === 'object') ? govde : readFormPayload();
        if (tabanIspTohumdaMi(g.base_isp)) {
            b.design_ambient = ortamKaydi(tabanIspOrtami);
        }
        return b;
    }

    window.AnalysisDock.register({
        id: 'performance',
        title: 'Advanced Performance — 3D Surface, Mach Contour, Heat Flux',
        titleKey: 'panel.performance.title',
        category: 'PERFORMANCE',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid'],
        fields: PERF_FIELDS,
        required: PERF_REQUIRED,
        fromResults: fromResults,
        contextFromResults: baglamSonuctan,
        render: render,
    });

    window.AnalysisDock.register({
        id: 'performance_solid',
        title: 'Advanced Performance — Mach Contour, Heat Flux',
        titleKey: 'panel.performance.titleSolid',
        category: 'PERFORMANCE',
        endpoint: ENDPOINT,
        motorTypes: ['solid'],
        fields: [['analysis_type', 'Figure', SOLID_FIGURES[0][0], SOLID_FIGURES,
                  'panel.performance.figChoice', 'panel.performance.help.analysis_type']].concat(
            PERF_FIELDS.filter(function (f) {
                return SURFACE_ONLY_FIELDS.indexOf(f[0]) === -1;
            })),
        required: PERF_REQUIRED.filter(function (k) {
            return SURFACE_ONLY_FIELDS.indexOf(k) === -1;
        }),
        fromResults: fromResults,
        render: renderSolid,
    });

    // Saf eşleme: motor sonucu -> form alanları. register() içindeki anonim
    // fonksiyondan çıkarıldı ki test doğrudan çağırabilsin.
    function fromResults(r) {
        const m = (r && r.motor) || r || {};
        const geo = (m.motor_geometry && typeof m.motor_geometry === 'object')
            ? m.motor_geometry : null;
        birimiCozulemeyenAlanlar = [];

        // 2026-08-03 (Faz 6, T18 kök nedeni): itici KİMLİĞİ hiçbir zaman
        // isteğe girmiyordu. Uç (app.py::advanced_performance_analysis)
        // `fuel_type` / `oxidizer_type` alanlarını zaten okuyor, ama panel
        // yalnız SAYISAL form alanlarını gönderiyordu — sonuçta RP-1/LOX
        // sayfasında bile denge yüzeyi N2O/HTPB referans çiftiyle çözülüyor,
        // üstüne o yüzeye ait olmayan bir tasarım noktası basılıyordu.
        // Kimlik burada yakalanır (motor sonucu tek doğruluk kaynağıdır) ve
        // readFormPayload her istekte ekler; arayüze yeni alan eklenmez,
        // kullanıcının elle tutarlı tutması gerekmez.
        sonIticiler = iticiKimligi(m);
        motorOrtamKaydi = (m.design_ambient && typeof m.design_ambient === 'object'
                           && typeof m.design_ambient.mode === 'string')
            ? ortamKaydi(ortamTanimi(m.design_ambient)) : null;
        const sug = {
            chamber_pressure: m.chamber_pressure,
            burn_time: m.burn_time,
            expansion_ratio: m.expansion_ratio,
            chamber_temperature: m.chamber_temperature,
            gamma: m.gamma,
        };
        const mw = ilkYolSayisi(m, MW_YOLLARI);
        if (mw !== null) sug.molecular_weight = mw;
        // O/F: üretici anahtar adları tipe göre değişir (bulgu 4) —
        // hibrit of_ratio, sıvı mixture_ratio / optimal_mixture_ratio.
        const of = firstFinite(m, ['of_ratio', 'mixture_ratio',
                                   'optimal_mixture_ratio']);
        if (of !== null) sug.optimal_of_ratio = of;

        // Uzunluklar SI'ya normalize edilir (bulgu 5)
        const chamberL = geoLength(m, geo, 'chamber_length', r);
        if (chamberL !== null) sug.chamber_length = chamberL;
        const chamberD = geoLength(m, geo, 'chamber_diameter', r);
        if (chamberD !== null) sug.chamber_diameter = chamberD;

        // base_isp: doğrudan isp (sıvıda isp_sea_level, katıda
        // specific_impulse); yoksa F/(ṁ·g0) türetilir
        const isp = firstFinite(m, ['isp', 'specific_impulse', 'isp_sea_level']);
        const thrust = firstFinite(m, ['thrust', 'average_thrust']);
        const mdot = firstFinite(m, ['mdot_total', 'total_mass_flow']);
        if (isp !== null) {
            sug.base_isp = isp;
        } else if (thrust !== null && mdot !== null && mdot > 0) {
            sug.base_isp = Number((thrust / (mdot * 9.80665)).toPrecision(5));
        }
        // V307/GÜVERTE-ORTAM: sıvıda deniz seviyesi dışındaki tasarımda
        // önerilen Temel Isp tasarım ortamının Isp'sidir (`specific_impulse`
        // = `isp_design_ambient`; sayı DEĞİŞMEDİ) — ortamı görünür notta.
        tabanIspOrtami = (sug.base_isp !== undefined) ? ortamTanimi(m.design_ambient) : null;
        tabanIspTohumu = (sug.base_isp !== undefined) ? sug.base_isp : null;
        tabanIspNotunuYaz();
        // Kütle debisi: yoksa Isp tanımından türetilir (ṁ = F/(Isp·g0))
        if (mdot !== null && mdot > 0) {
            sug.mdot_total = mdot;
        } else if (thrust !== null && isp !== null && isp > 0) {
            sug.mdot_total = Number((thrust / (isp * 9.80665)).toPrecision(6));
        }
        // V301/H-PANEL (NK-73): ıraksak lüle boyu çözücünün yayımladığı
        // değerden (design_summary.nozzle.divergent_length_mm, kaynak
        // nozzle_contour.divergent.length); yoksa alan boş kalır (uydurma yok).
        const noz = ((m.design_summary || {}).nozzle || {});
        if (typeof noz.divergent_length_mm === 'number'
                && isFinite(noz.divergent_length_mm) && noz.divergent_length_mm > 0) {
            sug.nozzle_length = Number((noz.divergent_length_mm / 1000).toPrecision(6));
        }
        // Backend alan (m²) ister; sonuçta çap var → A = π d²/4
        const throatD = geoLength(m, geo, 'throat_diameter', r);
        if (throatD !== null) {
            sug.throat_area = Number(
                (Math.PI * throatD * throatD / 4).toPrecision(6));
        }
        return sug;
    }

    // Test / hata ayıklama: saf yardımcılar (injector_panel deseni)
    window.PerformancePanel = {
        _render: render,
        _parseFigure: parseFigure,
        _readFormPayload: readFormPayload,
        _contextFromResults: baglamSonuctan,
        _propellantIdentity: iticiKimligi,
        //: OH-D32-01 — emekli `_siLength` çıkarımının yerine ADLI yokluk:
        //: son `fromResults` turunda birimi çözülemeyen alan adları.
        _unresolvedGeometry: function () {
            return birimiCozulemeyenAlanlar.slice();
        },
        // Birim sözleşmesi testi (tests/test_unit_contract.py) bu saf
        // fonksiyonu gerçek motor yanıtı üzerinde node ile çalıştırır.
        _fromResults: fromResults,
        //: V307/GÜVERTE-ORTAM — son fromResults turunda önerilen Temel
        //: Isp'nin tasarım ortamı (deniz seviyesinde null).
        _baseIspAmbient: function () { return tabanIspOrtami; },
    };
})();
