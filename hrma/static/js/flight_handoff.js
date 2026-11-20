/*
 * flight_handoff.js — Motor sayfası -> uçuş sahası (launch_site) oturum köprüsü.
 *
 * Amaç: Kullanıcı bir motor sayfasında (hibrit/katı/sıvı) başarılı bir hesap
 * yaptığında, sonucu tek Python normalize'ından (POST /api/flight-vehicle,
 * source:'results') geçirip normalize edilmiş "uçan araç"ı
 * localStorage['hrma.flight.lastVehicle']'e yazar. /launch-site ayrı bir sayfa
 * olduğundan (motor formu / currentResults YOK) motor oradan bu köprüyle taşınır.
 *
 * Bu dosya SADECE köprü mantığını tanımlar (window.FlightHandoff). Motor
 * HTML'lerine <script> etiketi ve publish() çağrısı EKLEMEK bu dosyanın işi
 * DEĞİLDİR (dosya sahipliği: D-frontend ajanı). launch_site tarafı
 * FlightHandoff.readLast() ile kaydı okur.
 *
 * WKWebView/pywebview'de localStorage çalışır (sixdof_panel.js:799 teyidi).
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'hrma.flight.lastVehicle';
    var ENDPOINT = '/api/flight-vehicle';

    /* V301/UÇUŞ NK-47 — SON YAYIMLANAN ARACIN HANGİ HESABA AİT OLDUĞU.
     * Motor sayfasının 6-DOF paneli "gövde bu motoru taşıyabilir mi"
     * hükmü için motorun dış zarfını (engine_od_m / engine_length_m) aynı
     * hesabın normalize edilmiş aracından alır; Fırlatma Sahası da aynı
     * alanları gönderir ve hüküm 6-DOF ucunda TEK işlevle verilir
     * (flight_vehicle.airframe_fit_conflicts). Eşleşme NESNE KİMLİĞİYLE
     * kurulur: araç yalnız o sonuç nesnesi (window.currentResults) için
     * döner, bayat bir hesabın aracı başka bir hesaba yapışmaz. */
    var lastPublished = { results: null, vehicle: null };

    /* V306/UÇUŞ-3 (SIVI-SOĞUTMA DEVİR) — ARAÇ KURULMADIYSA NEDENİ.
     * Motor kütlesini yayımlamayan sonuç için uç aracı adıyla reddeder
     * (422 ``engine_mass_not_published``). Ret, hangi hesaba ait olduğuyla
     * (nesne kimliği) tutulur; uçuş panelleri o hesapta sayfa motorunu
     * uçurmaz ve nedeni yazar. Önceki hesabın aracı da depodan kalkar —
     * Fırlatma Sahası eski motoru "son hesap" diye uçurmaz. */
    var REFUSAL_CODE = 'engine_mass_not_published';
    /* V307/FS-KÜÇÜK (kalem 4; SIVI-ORTAM DEVİR 3) — vakum/irtifa tasarımlı
     * sıvı motorun lülesi deniz seviyesinde ayrılıyorsa yerden kalkış itkisi
     * yayımlanmaz; uç aracı bu kodla ADIYLA reddeder (eskiden genel
     * 'unflyable_vehicle'). Ret kaydı metnin ihtiyaç duyduğu tasarım ortamı
     * ve deniz seviyesi alanlarını (uç yanıtından, aynen) taşır. */
    var REFUSAL_CODE_SEA_LEVEL = 'sea_level_thrust_not_published';
    var lastRefused = { results: null, body: null };

    /* V307/FS-OTURUM (kalem 1) — ÇALKANTI KAYNAĞI KÖPRÜ KAYDINDA.
     * Fırlatma Sahası 6-DOF'u çalkantıyı motor sayfasıyla AYNI blokla bağlar
     * ({motor_type, motor_sonucu, arac_duzeni}); kayıtlı proje / dosya
     * kaynağında motor sonucu köprünün yeniden hesabından gelir. Oturum
     * aracında (bu kayıt) motor sonucu YOKTU: aynı motor proje kaynağında
     * ÇKK / geçerlilik dışı hükmü alırken oturumda rijit ve "kararlı"
     * uçuyordu (iki kaynak, iki hüküm sınıfı; FS-YÜK AÇIK 2).
     *
     * Kayıt motor sonucunun TAMAMINI taşımaz (örnek sıvı 476 564 B, hibrit
     * 3 004 267 B; localStorage ~5 MB): yalnız çalkantı bağlamanın
     * (hrma.analysis.slosh_motor_baglanti.slosh_tanklari, içinde
     * flight_vehicle.normalize) motor sonucundan OKUDUĞU yaprakları taşır.
     * Liste ÖLÇÜLDÜ (okuma kaydeden sözlük; docs/scofield/raw/OH/V307/
     * fs-oturum/alan_olcumu.py) + aynı işlevlerin örnekte koşmayan dallarının
     * alanları. Bekçi (tests/test_v307_fs_oturum.py): ölçülen her okuma
     * listede; izdüşümle çalkantı çıktısı ve 6-DOF hükmü tam sonuçla
     * bit-aynı. Yol yaprağı ya da sözlük olmayan ara düğüm AYNEN kopyalanır.
     * Bu blok JSON'dur (test onu JSON olarak okur): satır ekleme/çıkarma
     * yalnız iki işaret arasında. */
    // CALKANTI_KAYNAK_YOLLARI_BASI
    var CALKANTI_KAYNAK_YOLLARI = {
        "liquid": [
            "status", "error", "motor_name", "motor.motor_name",
            "motor_geometry.motor_name", "thrust", "burn_time",
            "total_mass_flow", "engine_mass_estimate",
            "exit_diameter_mm", "exit_diameter",
            "design_ambient.is_sea_level",
            "nozzle_design.performance.ambient_pressure",
            "design_summary.performance.thrust_sl_N",
            "design_summary.masses.propellant_mass_kg",
            "design_summary.masses.engine_mass_kg",
            "design_summary.masses.dry_mass_kg",
            "design_summary.key_dimensions.overall_length_mm",
            "design_summary.key_dimensions.overall_length_with_closure_mm",
            "component_sizing.component_dimensions.overall_length",
            "component_sizing.not_in_engine_dry_mass",
            "oxidizer_flow", "fuel_flow", "mass_flow_ledger.status",
            "detailed_feed_system.valve_feedline.oxidizer_line.viscosity_Pa_s",
            "detailed_feed_system.valve_feedline.oxidizer_line.viscosity_source",
            "detailed_feed_system.valve_feedline.fuel_line.viscosity_Pa_s",
            "detailed_feed_system.valve_feedline.fuel_line.viscosity_source",
            "propellant_tanks.system_summary.ullage_fraction",
            "propellant_tanks.system_summary.total_tank_mass",
            "propellant_tanks.system_summary.total_propellant_mass",
            "propellant_tanks.system_summary.total_propellant_mass_nominal",
            "propellant_tanks.oxidizer_tank.propellant_type",
            "propellant_tanks.oxidizer_tank.dimensions.diameter",
            "propellant_tanks.oxidizer_tank.dimensions.length",
            "propellant_tanks.oxidizer_tank.dimensions.volume",
            "propellant_tanks.oxidizer_tank.pressure_vessel.wall_thickness_used_mm",
            "propellant_tanks.oxidizer_tank.pressure_vessel.head_thickness_available_mm",
            "propellant_tanks.oxidizer_tank.propellant_data.density",
            "propellant_tanks.oxidizer_tank.propellant_data.density_source",
            "propellant_tanks.oxidizer_tank.propellant_data.mass",
            "propellant_tanks.oxidizer_tank.propellant_data.mass_nominal",
            "propellant_tanks.oxidizer_tank.structural.tank_mass",
            "propellant_tanks.oxidizer_tank.slosh.radius",
            "propellant_tanks.oxidizer_tank.slosh.f1_hz",
            "propellant_tanks.oxidizer_tank.slosh.baffle.damping_ratio",
            "propellant_tanks.fuel_tank.propellant_type",
            "propellant_tanks.fuel_tank.dimensions.diameter",
            "propellant_tanks.fuel_tank.dimensions.length",
            "propellant_tanks.fuel_tank.dimensions.volume",
            "propellant_tanks.fuel_tank.pressure_vessel.wall_thickness_used_mm",
            "propellant_tanks.fuel_tank.pressure_vessel.head_thickness_available_mm",
            "propellant_tanks.fuel_tank.propellant_data.density",
            "propellant_tanks.fuel_tank.propellant_data.density_source",
            "propellant_tanks.fuel_tank.propellant_data.mass",
            "propellant_tanks.fuel_tank.propellant_data.mass_nominal",
            "propellant_tanks.fuel_tank.structural.tank_mass",
            "propellant_tanks.fuel_tank.slosh.radius",
            "propellant_tanks.fuel_tank.slosh.f1_hz",
            "propellant_tanks.fuel_tank.slosh.baffle.damping_ratio"
        ],
        "hybrid": [
            "status", "error", "motor_name", "motor_geometry.motor_name",
            "motor.motor_name", "motor.thrust", "motor.burn_time",
            "motor.uq_mode", "motor.exit_area", "motor.total_impulse",
            "motor.thrust_curve", "motor.mdot_ox",
            "motor.oxidizer_mass", "motor.fuel_mass", "motor.fuel_mass_loaded",
            "motor.propellant_mass_total",
            "motor.altitude_performance.nozzle_loss_model.exit_area_m2",
            "motor.nozzle_design.performance.ambient_pressure",
            "motor.oxidizer_inlet_state.oxidizer",
            "motor.design_summary.key_dimensions.dry_mass_basis",
            "motor.design_summary.key_dimensions.dry_mass_estimate_kg",
            "motor.design_summary.key_dimensions.total_motor_length_with_caps_mm",
            "motor.structural_analysis.chamber_analysis.diameter",
            "motor.structural_analysis.chamber_analysis.inner_diameter_mm",
            "motor.structural_analysis.chamber_analysis.wall_thickness_mm",
            "motor.structural_analysis.chamber_analysis.wall_thickness_used_mm",
            "motor.oxidizer_tank_pressure_vessel.pressure_vessel.wall_thickness_used_mm",
            "motor.oxidizer_tank_pressure_vessel.pressure_vessel.head_thickness_available_mm",
            "motor.oxidizer_tank_slosh.tank_diameter_m",
            "motor.oxidizer_tank_slosh.tank_length_m",
            "motor.oxidizer_tank_slosh.tank_volume_m3",
            "motor.oxidizer_tank_slosh.liquid_density_kg_m3",
            "motor.oxidizer_tank_slosh.liquid_fill_fraction",
            "motor.oxidizer_tank_slosh.liquid_mass_kg",
            "motor.oxidizer_tank_slosh.slosh.f1_hz",
            "motor.tank_blowdown.status",
            "motor.tank_blowdown.feed_mode",
            "motor.tank_blowdown.time_s",
            "motor.tank_blowdown.thrust_N",
            "motor.tank_blowdown.total_impulse_Ns",
            "motor.tank_blowdown.propellant_consumed_kg",
            "motor.tank_blowdown.oxidizer_inventory.liquid_mass_time_s",
            "motor.tank_blowdown.oxidizer_inventory.liquid_mass_kg",
            "motor.tank_blowdown.oxidizer_inventory.liquid_density_kg_m3",
            "motor.tank_blowdown.oxidizer_inventory.tank_initial_liquid_kg",
            "motor.tank_blowdown.oxidizer_inventory.tank_initial_vapour_kg",
            "motor.tank_blowdown.oxidizer_inventory.tank_final_kg"
        ]
    };
    // CALKANTI_KAYNAK_YOLLARI_SONU
    /* Kayıttaki bloğun biçim sürümü; Fırlatma Sahası başka sürümü OKUMAZ
     * (rijit uçar, nedeni yazılır). Yol listesi değişirse artırılır. */
    var CALKANTI_KAYNAK_SURUMU = 1;

    /* Motor sonucunun çalkantı izdüşümü (motor türünün yol listesi). Yol
     * kaynakta yoksa hedefte de yoktur (uydurma alan yok); yaprak ya da
     * sözlük olmayan ara düğüm aynen kopyalanır. Sıvı/hibrit değilse null. */
    function calkantiKaynagi(results, motorType) {
        var has = Object.prototype.hasOwnProperty;
        var yollar = has.call(CALKANTI_KAYNAK_YOLLARI, motorType)
            ? CALKANTI_KAYNAK_YOLLARI[motorType] : null;
        if (!yollar || !results || typeof results !== 'object' || Array.isArray(results)) return null;
        var out = {};
        yollar.forEach(function (yol) {
            var parca = yol.split('.');
            var kaynak = results, hedef = out;
            for (var i = 0; i < parca.length; i++) {
                var k = parca[i];
                if (!has.call(kaynak, k)) return;
                var v = kaynak[k];
                if (i === parca.length - 1 || v === null || typeof v !== 'object' || Array.isArray(v)) {
                    hedef[k] = v;
                    return;
                }
                if (!has.call(hedef, k)) hedef[k] = {};
                kaynak = v; hedef = hedef[k];
            }
        });
        return out;
    }

    /* Motor tipini belirle: açık değer > sayfa yolu (solid/liquid) > hibrit. */
    function detectMotorType(explicit) {
        if (explicit) return String(explicit).toLowerCase();
        var p = (window.location && window.location.pathname || '').toLowerCase();
        if (p.indexOf('solid') !== -1) return 'solid';
        if (p.indexOf('liquid') !== -1) return 'liquid';
        return 'hybrid'; // advanced.html (hibrit) varsayılan
    }

    /* Araç adı: #motor_name girdisi > yüklü projenin adı > sonuç sözlüğü >
       null (normalize doldurur). 3.0.7 (M7-FS-6 kalanı, ana model 20 Kas):
       sıvı sayfasında #motor_name yok ve sonuç sözlüğü iç ad taşıyor
       ("HRMA_LIQUID"); proje yüklüyse Fırlatma Sahası oturum aracını projenin
       adıyla gösterir (proje kaynağıyla aynı ad). */
    function resolveName(results, explicit) {
        if (explicit && String(explicit).trim()) return String(explicit).trim();
        try {
            var el = document.getElementById('motor_name');
            if (el && el.value && el.value.trim()) return el.value.trim();
        } catch (e) { /* DOM yoksa geç */ }
        try {
            var pb = window.HRMAProjectBar;
            var pn = (pb && typeof pb.currentName === 'function') ? pb.currentName() : null;
            if (pn && String(pn).trim()) return String(pn).trim();
        } catch (e) { /* proje çubuğu yoksa geç */ }
        if (results && typeof results === 'object') {
            var cands = [
                results.motor_name,
                results.motor && results.motor.motor_name,
                results.motor_geometry && results.motor_geometry.motor_name
            ];
            for (var i = 0; i < cands.length; i++) {
                if (cands[i] && String(cands[i]).trim()) return String(cands[i]).trim();
            }
        }
        return null;
    }

    /*
     * Motor sayfası tarafından hesap BAŞARISINDA çağrılır.
     *   results : window.currentResults (hibrit: {motor:{...}, ...};
     *             katı/sıvı: düz sonuç sözlüğü).
     *   opts    : { motor_type?, motor_name? } — ikisi de opsiyonel.
     * Dönüş: kaydedilen kaydı çözen Promise (hata/araç yoksa null).
     * Hesap akışını ASLA bozmaz: her hata sessizce yutulur (uçuş sayfası
     * araç yoksa örnek araca düşer).
     */
    function publish(results, opts) {
        opts = opts || {};
        if (!results || typeof results !== 'object') {
            return Promise.resolve(null);
        }
        var motorType = detectMotorType(opts.motor_type);
        var name = resolveName(results, opts.motor_name);
        var payload = {
            source: 'results',
            motor_type: motorType,
            motor_name: name,
            results: results
        };

        return fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function (r) {
            if (!r.ok) {
                return r.json().catch(function () { return null; }).then(function (b) {
                    if (r.status === 422 && b && (b.error === REFUSAL_CODE
                            || b.error === REFUSAL_CODE_SEA_LEVEL)) {
                        lastRefused = { results: results, body: b };
                        lastPublished = { results: null, vehicle: null };
                        try {
                            window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
                                refused: { code: b.error, cause: b.cause || null,
                                           design_ambient: b.design_ambient || null,
                                           sea_level: b.sea_level || null,
                                           motor_name: name || null, motor_type: motorType },
                                saved_at: new Date().toISOString()
                            }));
                        } catch (e) { /* depo kapalı */ }
                        try {
                            if (typeof document !== 'undefined' && document.dispatchEvent
                                    && typeof CustomEvent === 'function') {
                                document.dispatchEvent(new CustomEvent('hrma:flight-vehicle-refused',
                                    { detail: { results: results, refusal: b } }));
                            }
                        } catch (e) { /* olay yoksa paneller vehicleRefusalText ile okur */ }
                    }
                    throw new Error('flight-vehicle HTTP ' + r.status);
                });
            }
            return r.json();
        }).then(function (data) {
            // Route {status, vehicle} ya da doğrudan araç döndürebilir.
            var vehicle = (data && data.vehicle) ? data.vehicle : data;
            if (!vehicle || typeof vehicle !== 'object') return null;
            lastPublished = { results: results, vehicle: vehicle };
            if (lastRefused.results === results) lastRefused = { results: null, body: null };
            // NK-14/NK-47: aynı sayfanın panelleri (yörünge, 6-DOF) aracı
            // beklemeden kurulur; araç gelince haber verilir ki kütleler ve
            // motor zarfı TEK kaynaktan (sunucu normalize) tohumlansın.
            try {
                if (typeof document !== 'undefined' && document.dispatchEvent
                        && typeof CustomEvent === 'function') {
                    document.dispatchEvent(new CustomEvent('hrma:flight-vehicle',
                        { detail: { results: results, vehicle: vehicle } }));
                }
            } catch (e) { /* olay yayımlanamazsa paneller vehicleFor ile okur */ }
            var record = {
                vehicle: vehicle,
                motor_name: vehicle.motor_name || name || null,
                motor_type: motorType,
                saved_at: new Date().toISOString()
            };
            // V307/FS-YÜK: aynı sayfanın 6-DOF panelindeki faydalı yük
            // (Fırlatma Sahası alanları bununla dolar; boşsa alan yok).
            var yuk = panelPayload();
            if (yuk) record.payload = yuk;
            // V307/FS-OTURUM (kalem 1): çalkantı kaynağı (yalnız sıvı/hibrit;
            // yukarıdaki yol listesinin izdüşümü). Depo bloğu almazsa kayıt
            // bloksuz yazılır ve neden kayıtta adıyla durur (Fırlatma Sahası
            // rijit uçar, nedeni yazar); araç kaybolmaz.
            var kaynak = calkantiKaynagi(results, motorType);
            if (kaynak) {
                record.calkanti_kaynagi = { surum: CALKANTI_KAYNAK_SURUMU,
                                            motor_type: motorType, motor_sonucu: kaynak };
            }
            try {
                window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
                buSayfaninKaydi = record.saved_at;
            } catch (e) {
                if (!record.calkanti_kaynagi) { /* storage kapalı/dolu olabilir */ return record; }
                delete record.calkanti_kaynagi;
                record.calkanti_kaynagi_yazilamadi = true;
                try {
                    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
                    buSayfaninKaydi = record.saved_at;
                } catch (e2) { /* storage kapalı/dolu olabilir */ }
            }
            return record;
        }).catch(function (e) {
            if (window.console && console.debug) {
                console.debug('flight_handoff.publish:', e && e.message ? e.message : e);
            }
            return null;
        });
    }

    /* launch_site tarafı: son köprülenen aracı oku (yoksa null).
     *
     * ÖH D21 / P12aB4-22 — ÖLÇÜLEN KUSUR: bu fonksiyonun ürün tarafında HİÇ
     * çağrısı yoktu; launch_site.html depolama anahtarını KENDİ yeniden
     * bildirip (`var HANDOFF_KEY = ...`) doğrudan localStorage'a gidiyordu —
     * aynı anahtarın iki kaynağı, biri değişirse köprü sessizce kopardı.
     *
     * Çağrıya bağlanabilmesi için tek eksik parça durum ayrımıydı: eski gövde
     * "kayıt yok" ile "kayıt var ama çözülemedi" durumlarının İKİSİNDE de
     * null dönüyordu ve tüketici bozuk kaydı "henüz hesap yapılmamış" diye
     * raporlardı (sessiz yedek). `out` verilirse `out.status` doldurulur:
     *   'empty'      — kayıt yok (temiz durum)
     *   'unreadable' — kayıt var ama okunamadı/çözülemedi (depolama kapalı
     *                  olması da buraya girer: "okunamadı" bilgisi doğrudur)
     *   'ok'         — kayıt çözüldü
     * Dönüş sözleşmesi değişmedi: kayıt ya da null.
     */
    function readLast(out) {
        var durum = 'empty', kayit = null;
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            if (raw) {
                try {
                    kayit = JSON.parse(raw);
                    durum = kayit ? 'ok' : 'unreadable';
                    // V306/UÇUŞ-3: son hesabın aracı adıyla reddedildi.
                    if (kayit && kayit.refused && !kayit.vehicle) {
                        if (out) out.refusal = kayit.refused;
                        durum = 'refused';
                    }
                } catch (e) {
                    durum = 'unreadable';
                }
            }
        } catch (e) {
            durum = 'unreadable';
        }
        if (out) out.status = durum;
        return durum === 'ok' ? kayit : null;
    }

    /* V307/FS-YÜK — FAYDALI YÜK KÖPRÜSÜ. Motor sayfasının 6-DOF panelindeki
     * faydalı yük alanları (SixDofPanel.payloadForFlight) son hesabın kaydına
     * `payload` olarak girer; Fırlatma Sahası oturum aracında alanlarını
     * bundan doldurur (kayıtlı projede uç aynı bloğu belgeden kurar:
     * flight_vehicle.project_payload). Panel alanı hesaptan SONRA
     * değişirse syncPayload kaydı günceller — yalnız kayıt BU sayfanın son
     * yayımıysa (başka motor sayfasının aracına başka panelin yükü yazılmaz).
     */
    var buSayfaninKaydi = null;   // bu sayfanın yazdığı kaydın saved_at'i
    function panelPayload() {
        try {
            var p = (window.SixDofPanel && typeof window.SixDofPanel.payloadForFlight === 'function')
                ? window.SixDofPanel.payloadForFlight() : null;
            return (p && typeof p === 'object') ? p : null;
        } catch (e) { return null; }
    }
    function syncPayload() {
        if (!buSayfaninKaydi) return false;
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            var kayit = raw ? JSON.parse(raw) : null;
            if (!kayit || !kayit.vehicle || kayit.saved_at !== buSayfaninKaydi) return false;
            var yuk = panelPayload();
            if (yuk) kayit.payload = yuk; else delete kayit.payload;
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(kayit));
            return true;
        } catch (e) { return false; }
    }

    /* Köprüyü temizle (yeni saha/araç seçilince entegratör çağırabilir). */
    function clear() {
        try { window.localStorage.removeItem(STORAGE_KEY); } catch (e) { /* geç */ }
    }

    /* V301/UÇUŞ NK-14 / NK-24 — HESAPTAN SONRA MOTOR FORMU DEĞİŞTİ Mİ?
     * Hibrit sayfa (app.js yorungeIcinDegisenMotorAlanlari) yörüngeyi bayat
     * motorla koşmuyordu; katı ve sıvı sayfaları koşuyordu (ölçüldü:
     * nk_paneller_sonra.json — katıda Pc 40 -> 55, sıvıda itki 25 -> 30 kN
     * değiştirilip hesaplanmadan yörünge 200 aldı, eski motorla). Tek yardımcı:
     * son hesabın form anlığı ile bugünkü formu karşılaştırır; çözücünün
     * OKUMADIĞINI kendisi beyan ettiği alanlar (results.unwired_inputs her
     * kategori + results.inputs_not_used) motoru değiştirmediği için dışarıda
     * kalır. Dönüş: değişen alan adları (sıralı) ya da anlık yoksa null. */
    function changedMotorFields(lastForm, nowForm, results) {
        if (!lastForm || typeof lastForm !== 'object') return null;
        var haric = {};
        var uw = results && results.unwired_inputs;
        if (uw && typeof uw === 'object') {
            Object.keys(uw).forEach(function (k) {
                (Array.isArray(uw[k]) ? uw[k] : []).forEach(function (f) {
                    var ad = (typeof f === 'string') ? f : (f && f.field);
                    if (ad) haric[ad] = true;
                });
            });
        }
        (Array.isArray(results && results.inputs_not_used) ? results.inputs_not_used : [])
            .forEach(function (f) {
                var ad = (typeof f === 'string') ? f : (f && f.field);
                if (ad) haric[ad] = true;
            });
        var simdi = nowForm || {};
        return Object.keys(Object.assign({}, lastForm, simdi)).filter(function (k) {
            return !haric[k] && JSON.stringify(lastForm[k]) !== JSON.stringify(simdi[k]);
        }).sort();
    }

    /* V306/UÇUŞ-3: verilen hesabın aracı adıyla reddedildiyse ekran metni,
     * değilse null. Metin uç yanıtının nedeninden (soğutma devresi çözülmedi
     * ya da motor kütlesi yayımlanmadı) sözlükle kurulur. */
    /* V307/FS-KÜÇÜK (kalem 4): tasarım ortamının adı (uç yanıtının
     * design_ambient bloğundan; sayı motorundur). */
    function tasarimOrtami(da) {
        da = da || {};
        if (da.mode === 'vacuum') return tr_('flight.ambientVacuum', 'vacuum');
        if (da.mode === 'altitude' && typeof da.altitude_m === 'number' && isFinite(da.altitude_m)) {
            return trf_('flight.ambientAltitude', { alt: sayiYaz(da.altitude_m, 0) }, '{alt} m altitude');
        }
        if (da.mode === 'pressure' && typeof da.pressure_bar === 'number' && isFinite(da.pressure_bar)) {
            return trf_('flight.ambientPressure', { p: sayiYaz(da.pressure_bar, 4) }, 'an ambient pressure of {p} bar');
        }
        return tr_('flight.ambientNonSeaLevel', 'a non-sea-level ambient');
    }
    function refusalText(body) {
        if (!body) return null;
        // Uç gövdesi `error`, köprü kaydı (readLast().refusal) `code` taşır.
        if ((body.error || body.code) === REFUSAL_CODE_SEA_LEVEL) {
            var ds = body.sea_level || {};
            var sayi = function (v) { return (typeof v === 'number' && isFinite(v)) ? sayiYaz(v, 4) : '—'; };
            return (body.cause === 'nozzle_flow_separated_at_sea_level')
                ? trf_('flight.refusedSeaLevelSeparated',
                    { ambient: tasarimOrtami(body.design_ambient),
                      pe: sayi(ds.exit_pressure_bar), psep: sayi(ds.separation_pressure_bar) },
                    'No flight: this engine is designed for {ambient}; at sea level its nozzle flow separates (exit pressure {pe} bar, below the separation pressure {psep} bar), so no lift-off thrust is published, no vehicle is built and nothing is flown from the ground. Flying it as an upper stage ignited at altitude is not part of this flight.')
                : trf_('flight.refusedSeaLevelNotPublished',
                    { ambient: tasarimOrtami(body.design_ambient) },
                    'No flight: this engine is designed for {ambient} and its sea-level (lift-off) thrust is not published for this design, so no vehicle is built and nothing is flown from the ground.');
        }
        return (body.cause === 'cooling_circuit_not_solved')
            ? tr_('flight.refusedCooling',
                'No flight: the engine mass is not published for this calculation because the regenerative cooling circuit was not solved, so no vehicle is built and nothing is flown. Fix the cooling design and calculate again.')
            : tr_('flight.refusedEngineMass',
                'No flight: this engine calculation does not publish the engine mass, so no vehicle is built and nothing is flown.');
    }
    function vehicleRefusalText(results) {
        return (results && lastRefused.results === results) ? refusalText(lastRefused.body) : null;
    }

    /* NK-47: verilen sonuç nesnesinin (aynı hesap) normalize aracı ya da null. */
    function vehicleFor(results) {
        return (results && lastPublished.results === results)
            ? lastPublished.vehicle : null;
    }

    /* V306/UÇUŞ-2 — UÇUŞ İTKİSİ GİZLİ DURUMA BAĞLI OLAMAZ. Yörünge ve 6-DOF
     * panelleri uçuşa giren itkiyi (eğri, harcanan itici, A_e, p_ref) aynı
     * hesabın normalize aracından (flight_vehicle.motor_flight_thrust) alır.
     * Araç yayımı hesaptan sonra arka planda yapılır; koşu ondan önce
     * gelirse bu işlev aynı sonucu yayımlayıp aracı bekler. Böylece "araç
     * henüz gelmedi" diye başka bir itkiye düşülmez. Araç alınamazsa null. */
    function vehicleReady(results, opts) {
        var hazir = vehicleFor(results);
        if (hazir) return Promise.resolve(hazir);
        if (!results || typeof results !== 'object') return Promise.resolve(null);
        return publish(results, opts).then(function () {
            return vehicleFor(results);
        });
    }

    /* ------------------------------------------------------------------
     * V306/UÇUŞ NR-10 / NR-13 — "KULLANICI YAZDI" YALNIZ GERÇEK YAZMADIR.
     *
     * ÖLÇÜLDÜ (docs/scofield/raw/OH/V306/ucus/olcum_paneller_*_once.json):
     * örnek proje açılınca katı ve sıvı yörünge kütle alanları
     * data-user-override="true" taşıyordu; kullanıcı hiçbir şey yazmamıştı.
     * Kök: proje geri yüklemesi (project_bar.js dispatchFieldEvents) her
     * alana YAPAY 'input' olayı yayar; sayfaların "elle yazıldı" dinleyicisi
     * onu da sayıyordu. Sonuç: tasarım değeri bir daha yazılmıyordu —
     * sıvıda yörünge 156,313 kg (örnek dosyanın eski sayısı) ⟷ 6-DOF ve
     * Fırlatma Sahası 158,191 kg (NR-13); katıda yakıt değişince kütleler
     * eski KNDX'te kaldı ve yörünge "itici kütlesi tutmuyor" dedi (NR-10).
     * Kural: yalnız güvenilir (isTrusted) olay kullanıcının yazmasıdır. */
    function isUserEdit(e) { return !!(e && e.isTrusted); }

    function sayiYaz(v, n) {
        var I = window.I18N;
        return (I && typeof I.number === 'function') ? I.number(v, n) : v.toFixed(n);
    }
    function tr_(k, fb) {
        var I = window.I18N;
        return (I && typeof I.t === 'function') ? I.t(k, fb) : fb;
    }
    function trf_(k, p, fb) {
        var I = window.I18N;
        if (I && typeof I.tf === 'function') return I.tf(k, p, fb);
        return String(fb).replace(/\{(\w+)\}/g, function (b, ad) {
            return (p && ad in p) ? String(p[ad]) : b;
        });
    }
    function pozitif(v) { return typeof v === 'number' && isFinite(v) && v > 0; }
    /* Kütle alanları 3 ondalıkla yazılır (seedField d = 3); bu çözünürlüğün
     * yarısından küçük fark "aynı kütle" sayılır. Kalem satırı, itici bütçesi
     * satırı ve sıvı 6-DOF itici denetimi bu TEK eşiği kullanır. */
    var MASS_FIELD_TOL_KG = 0.5 * Math.pow(10, -3);

    /* Tasarımdan dolan alan (V306/UÇUŞ NR-10). Kullanıcı yazmadıysa tasarım
     * değeri yazılır (değer yoksa alan BOŞALIR: motora ait olmayan sayı
     * ekranda durmaz). Kullanıcı yazdıysa değeri EZİLMEZ; tasarım değeri
     * farklıysa alanın hemen altında açıkça yazılır ve tek tıkla alınabilir
     * (sessizce ezilmez, sessizce bayat kalmaz). Dönüş: alanda kalan sayı. */
    function seedField(el, value, digits, unit) {
        if (!el) return null;
        var d = (typeof digits === 'number') ? digits : 3;
        var notId = el.id + '_tasarim_notu';
        var not = document.getElementById(notId);
        var deger = pozitif(value) ? value : null;
        if (el.dataset.userOverride !== 'true') {
            el.value = (deger === null) ? '' : deger.toFixed(d);
            if (not) not.remove();
            el.classList.remove('ucus-elle-farkli');
            return deger;
        }
        var simdi = parseFloat(el.value);
        var farkli = deger !== null && !(isFinite(simdi)
            && Math.abs(simdi - deger) < 0.5 * Math.pow(10, -d));
        el.classList.toggle('ucus-elle-farkli', farkli);
        if (!farkli) { if (not) not.remove(); return isFinite(simdi) ? simdi : null; }
        if (!not) {
            not = document.createElement('div');
            not.id = notId;
            not.className = 'ucus-tasarim-notu';
            not.style.cssText = 'font-size:12px; line-height:1.4; margin-top:4px;'
                + ' color:var(--hd-orange, #ff8c33); white-space:normal;';
            el.insertAdjacentElement('afterend', not);
        }
        not.textContent = '';
        var metin = document.createElement('span');
        metin.textContent = trf_('flight.manualDiffers',
            { value: sayiYaz(deger, d), unit: unit || '' },
            'You typed this value, so it is kept. The current design gives {value} {unit}.') + ' ';
        var dugme = document.createElement('button');
        dugme.type = 'button';
        dugme.className = 'ucus-tasarim-al';
        dugme.style.cssText = 'font-size:12px; padding:1px 8px; margin-top:2px; cursor:pointer;';
        dugme.textContent = tr_('flight.useDesignValue', 'Use the design value');
        dugme.addEventListener('click', function () {
            delete el.dataset.userOverride;
            el.classList.remove('ucus-elle-farkli');
            el.value = deger.toFixed(d);
            if (not.parentNode) not.parentNode.removeChild(not);
            // Bağımlı dinleyiciler tazelensin; yapay olay "elle yazıldı" sayılmaz.
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        });
        not.appendChild(metin);
        not.appendChild(dugme);
        return isFinite(simdi) ? simdi : null;
    }

    /* V306/UÇUŞ NR-13 — MOTORUN UÇAN ATIL KÜTLESİ, KALEMİYLE. Üç panelin
     * kuru kütlesi aynı araçtan (vehicleFor) gelir; bu satır o sayıyı
     * kalemleriyle (flight_vehicle.engine_inert_mass_items) yazar. Alanın
     * değeri motorun atıl kütlesinden farklıysa fark da kalemiyle yazılır
     * (hibritte yörüngenin kuru kütlesi aracın kuru kütlesidir: motor +
     * gövde + faydalı yük). Araç ya da kalem yoksa boş dize (iddia yok). */
    /* V306/SIVI-KÜTLE: araç kaleminin sözlük yüklenmemişken yedek adı
     * (sözlükteki EN metnin aynısı; ham anahtar ekrana çıkmasın). */
    var ARAC_KALEMI_EN = {
        controls_avionics: 'controls / avionics (controller box, harness, sensors)'
    };
    function inertLedgerText(vehicle, fieldKg) {
        if (!vehicle || !pozitif(vehicle.engine_inert_mass)) return '';
        var toplam = vehicle.engine_inert_mass;
        var kalemler = Array.isArray(vehicle.engine_inert_mass_items)
            ? vehicle.engine_inert_mass_items : [];
        var parca = kalemler.filter(function (k) {
            return k && typeof k.key === 'string' && pozitif(k.mass_kg);
        }).map(function (k) {
            return trf_('flight.inertItem.' + k.key, { m: sayiYaz(k.mass_kg, 3) },
                k.key + ' {m} kg');
        });
        var satir = (parca.length > 1)
            ? trf_('flight.inertLedger',
                { items: parca.join(' + '), total: sayiYaz(toplam, 3) },
                'Engine flying inert mass: {items} = {total} kg')
            : trf_('flight.inertLedgerSingle',
                { item: parca.length ? parca[0] : (sayiYaz(toplam, 3) + ' kg') },
                'Engine flying inert mass: {item}');
        if (pozitif(fieldKg) && Math.abs(fieldKg - toplam) >= MASS_FIELD_TOL_KG) {
            var fark = fieldKg - toplam;
            satir += '. ' + (fark > 0
                ? trf_('flight.inertLedgerAbove',
                    { value: sayiYaz(fieldKg, 3), total: sayiYaz(toplam, 3),
                      diff: sayiYaz(fark, 3) },
                    'This field {value} kg = engine {total} kg + {diff} kg not from the engine (airframe, payload — your input).')
                : trf_('flight.inertLedgerBelow',
                    { value: sayiYaz(fieldKg, 3), diff: sayiYaz(-fark, 3) },
                    'This field {value} kg is {diff} kg BELOW the engine flying inert mass: a vehicle cannot weigh less than its engine.'));
        }
        // V306/SIVI-KÜTLE (M-SIVI-1): motor kuru kütlesinden çıkan araç
        // kalemi (kumanda / aviyonik) ADIYLA yazılır; kütlesi yoktur (HRMA
        // tahmin etmez), toplamın dışındadır — sessizce kaybolmaz.
        var disarida = (Array.isArray(vehicle.vehicle_items_not_in_engine)
            ? vehicle.vehicle_items_not_in_engine : []).filter(function (k) {
                return k && typeof k.key === 'string';
            }).map(function (k) {
                return tr_('flight.vehicleItem.' + k.key,
                    ARAC_KALEMI_EN[k.key] || k.key);
            });
        if (disarida.length) {
            satir += (/\.$/.test(satir) ? ' ' : '. ') + trf_('flight.notInEngine', { items: disarida.join(', ') },
                'Not in the engine mass: {items}, a vehicle item HRMA does not estimate; include it in the dry mass you enter.');
        }
        return satir;
    }

    /* Kalem satırını alanın altına basar/günceller (yoksa kurar). */
    function renderInertLedger(inputEl, vehicle) {
        if (!inputEl) return;
        var id = inputEl.id + '_kutle_kalemi';
        var kutu = document.getElementById(id);
        var metin = inertLedgerText(vehicle, parseFloat(inputEl.value));
        if (!metin) { if (kutu) kutu.remove(); return; }
        if (!kutu) {
            kutu = document.createElement('div');
            kutu.id = id;
            kutu.className = 'ucus-kutle-kalemi';
            kutu.style.cssText = 'font-size:12px; line-height:1.4; margin-top:4px;'
                + ' color:var(--hd-ink-dim, #7d97a5); white-space:normal;';
            var not = document.getElementById(inputEl.id + '_tasarim_notu');
            (not || inputEl).insertAdjacentElement('afterend', kutu);
        }
        kutu.textContent = metin;
        var asagi = (pozitif(parseFloat(inputEl.value))
            && parseFloat(inputEl.value) < vehicle.engine_inert_mass - MASS_FIELD_TOL_KG);
        kutu.style.color = asagi ? 'var(--hd-orange, #ff8c33)' : 'var(--hd-ink-dim, #7d97a5)';
    }

    /* ------------------------------------------------------------------
     * V306/UÇUŞ-2 — YÖRÜNGE PANELİNİN KÜNYESİ (üç motor sayfası, TEK işlev).
     *
     * Mühendis turu (2 Kas): yörünge paneli hangi itkiyle uçtuğunu, itkiyi
     * irtifaya göre düzeltip düzeltmediğini, düzlemsel model ve gizli 85°
     * atış açısını, "yük çarpanı"nın ne olduğunu söylemiyordu (M-HIBRIT-24,
     * M-KATI-26/-28); kalkamayan aracı zemin altına batarken çiziyordu
     * (M-KATI-29). Satırlar YALNIZ ucun yanıtından kurulur (sayı uydurulmaz);
     * yanıtta olmayan büyüklüğün satırı basılmaz.
     *   plotEl : grafiğin çizildiği öğe (künye hemen ardına konur)
     *   d      : /api/trajectory-analysis yanıtı (null → künye temizlenir)
     *   kaynak : uçan itkinin adı (motor_regulated | motor_blowdown |
     *            motor_thrust_curve | motor_constant), yoksa yazılmaz
     *   ucus   : (isteğe bağlı) aracın flight_thrust bloğu; motorun
     *            yayımladığı impuls uçandan farklıysa ikisi nedeniyle yazılır
     * Dönüş: grafik çizilsin mi (kalkış yoksa false) ve kalkış yok metni. */
    var KAYNAK_ANAHTARI = {
        motor_regulated: ['sixdof.srcMotorRegulated', 'ENGINE CURVE (regulated feed)'],
        motor_blowdown: ['sixdof.srcMotorBlowdown', 'ENGINE CURVE (N2O tank blowdown)'],
        motor_thrust_curve: ['sixdof.srcMotorCurve', 'ENGINE THRUST CURVE'],
        motor_constant: ['sixdof.srcMotorConstant', 'ENGINE THRUST (constant)']
    };
    /* V306/UÇUŞ-3 (M-SIVI-3) — YAZILAN KÜTLELER MOTORUN İTİCİSİYLE ÇELİŞİRSE.
     * Sıvı yörünge yanma süresini (İlk − Son Kütle) / ṁ ile türetir; iki
     * kütleyi de kullanıcı yazdıysa ve motor sonra değiştiyse fark itici
     * bütçesinden kopar ve yanma süresi SESSİZCE kısalır/uzar (ölçüldü 4 Kas:
     * motor 15 s / 148,725 kg, uçan 297,451 kg, 30,00 s — impuls motorun iki
     * katı, uyarı yok). Satır hangi değerin uçtuğunu adıyla yazar; sayı
     * hesaplanmaz, verilenler karşılaştırılır. Dönüş: [metin, 'warn'] ya da null. */
    function propellantBudgetLine(flownKg, engineKg, mdot) {
        if (!pozitif(flownKg) || !pozitif(engineKg) || !pozitif(mdot)) return null;
        if (Math.abs(flownKg - engineKg) < MASS_FIELD_TOL_KG) return null;
        return [trf_('flight.traj.propBudgetDiffers',
            { flown: sayiYaz(flownKg, 3), engine: sayiYaz(engineKg, 3),
              tb: sayiYaz(flownKg / mdot, 2), tbe: sayiYaz(engineKg / mdot, 2) },
            'Propellant flown = Initial − Final Mass = {flown} kg, but the engine carries {engine} kg: this trajectory burns {tb} s, not the engine burn time {tbe} s. The masses you typed are kept; correct them (airframe and payload go into both masses) or use the design values.'),
            'warn'];
    }

    function renderTrajectoryNotes(plotEl, d, kaynak, ucus, onSatirlar) {
        var sonuc = { draw: true, message: null };
        if (!plotEl || !plotEl.parentNode || typeof document === 'undefined') return sonuc;
        var id = (plotEl.id || 'trajectory') + '_kunye';
        var el = document.getElementById(id);
        if (!d) { if (el) el.textContent = ''; return sonuc; }
        if (!el) {
            el = document.createElement('div');
            el.id = id;
            el.className = 'help-text';
            el.style.cssText = 'font-family:var(--hd-mono); font-size:0.75rem; '
                + 'line-height:1.5; margin:6px 0 10px; white-space:normal;';
            plotEl.parentNode.insertBefore(el, plotEl.nextSibling);
        }
        var satirlar = (Array.isArray(onSatirlar) ? onSatirlar : []).filter(function (x) {
            return Array.isArray(x) && typeof x[0] === 'string' && x[0];
        });
        var td = (d && d.trajectory_data) || {};
        if (d.plot_withheld_because === 'no_liftoff') {
            var tw = d.no_liftoff && d.no_liftoff.thrust_to_weight_at_ignition;
            sonuc.draw = false;
            sonuc.message = trf_('flight.traj.noLiftoff',
                { tw: pozitif(tw) ? sayiYaz(tw, 3) : '—' },
                'NO LIFTOFF — thrust-to-weight at ignition is {tw} (it must be above 1): the vehicle does not leave the pad, so there is no trajectory to draw.');
            satirlar.push([sonuc.message, 'err']);
        }
        var ti = td.thrust_input;
        var ed = d.engine_data || {};
        var imp = (ti && pozitif(ti.total_impulse_Ns)) ? ti.total_impulse_Ns
            : (pozitif(ed.total_impulse) ? ed.total_impulse : null);
        var kEt = kaynak && KAYNAK_ANAHTARI[kaynak];
        if (kEt && imp !== null) {
            var impSatiri = trf_('flight.traj.thrust',
                { src: tr_(kEt[0], kEt[1]), imp: sayiYaz(imp, 0) },
                'Thrust flown: {src}, total impulse {imp} N·s; the 6-DOF panel flies the same thrust when its thrust source is the page calculation.');
            // V306/UÇUŞ-2: motorun yayımladığı impuls uçandan farklıysa
            // (ölçüldü: hibrit N₂O boşalma serisi t > 0'da başlıyor) ikisi
            // yan yana ve nedeniyle (tek büyüklük, tek sayı).
            var mYayin = ucus && ucus.motor_published_impulse_ns;
            var egri = ucus && ucus.thrust_curve;
            var t0 = (egri && Array.isArray(egri.time) && egri.time.length) ? Number(egri.time[0]) : null;
            if (pozitif(mYayin) && t0 !== null && t0 > 0
                    && Math.abs(imp - mYayin) > 1e-4 * mYayin) {
                impSatiri += ' (' + trf_('flight.traj.impulseMotorDiff',
                    { m: sayiYaz(mYayin, 0), t0: sayiYaz(t0, 3) },
                    'the engine publishes {m} N·s: its curve starts at t = {t0} s and the flight holds the first thrust value from ignition (t = 0)') + ')';
            }
            satirlar.push([impSatiri, '']);
        }
        var tac = td.thrust_altitude_compensation;
        if (tac && tac.modelled === true && pozitif(tac.nozzle_exit_area_m2)
                && pozitif(tac.reference_pressure_pa)) {
            satirlar.push([trf_('flight.traj.altComp',
                { ae: sayiYaz(tac.nozzle_exit_area_m2 * 1e4, 2),
                  p: sayiYaz(tac.reference_pressure_pa, 0) },
                'Thrust corrected for altitude: F(h) = F_ref + (p_ref − p_a)·A_e, A_e = {ae} cm², p_ref = {p} Pa.'), '']);
        } else if (tac && tac.modelled === false) {
            satirlar.push([tr_('flight.traj.altCompOff',
                'Thrust NOT corrected for altitude: no nozzle exit area, so it stays at its reference value.'), 'warn']);
        }
        var tm = (td.performance && td.performance.trajectory_metrics) || {};
        if (sonuc.draw && pozitif(tm.max_load_factor_g)
                && pozitif(tm.max_kinematic_acceleration_g)) {
            satirlar.push([trf_('flight.traj.loadFactor',
                { n: sayiYaz(tm.max_load_factor_g, 2),
                  k: sayiYaz(tm.max_kinematic_acceleration_g, 2) },
                'Peak load factor (sensed acceleration, gravity excluded) {n} g; peak kinematic acceleration |dv/dt| {k} g.'), '']);
        }
        var fm = td.flight_model;
        if (fm && typeof fm.launch_angle_deg === 'number') {
            satirlar.push([trf_('flight.traj.model',
                { a: sayiYaz(fm.launch_angle_deg, 1),
                  src: fm.launch_angle_source === 'supplied'
                      ? tr_('flight.traj.angleSupplied', 'entered on this panel')
                      : tr_('flight.traj.angleDefault', 'not entered — HRMA default') },
                'Planar (2-D) point-mass model: flight in the vertical plane, no attitude dynamics; launch angle {a}° from horizontal ({src}).'), '']);
            satirlar.push([tr_('flight.traj.modelDiff',
                'With the same thrust the 6-DOF panel adds attitude dynamics (the vehicle turns into the wind) and uses its own drag coefficient, body diameter, launch angle, rail and wind; its apogee differs from this planar model for those reasons.'), '']);
        }
        el.textContent = '';
        satirlar.forEach(function (sat) {
            var s = document.createElement('div');
            s.textContent = sat[0];
            if (sat[1] === 'err') s.style.color = 'var(--hd-red, #ff5d73)';
            else if (sat[1] === 'warn') s.style.color = 'var(--hd-amber, #ffbe46)';
            el.appendChild(s);
        });
        return sonuc;
    }

    window.FlightHandoff = {
        resolveName: resolveName,
        isUserEdit: isUserEdit,
        vehicleRefusalText: vehicleRefusalText,
        refusalText: refusalText,
        REFUSAL_CODES: [REFUSAL_CODE, REFUSAL_CODE_SEA_LEVEL],
        seedField: seedField,
        inertLedgerText: inertLedgerText,
        renderInertLedger: renderInertLedger,
        publish: publish,
        vehicleFor: vehicleFor,
        vehicleReady: vehicleReady,
        renderTrajectoryNotes: renderTrajectoryNotes,
        propellantBudgetLine: propellantBudgetLine,
        MASS_FIELD_TOL_KG: MASS_FIELD_TOL_KG,
        changedMotorFields: changedMotorFields,
        readLast: readLast,
        syncPayload: syncPayload,
        calkantiKaynagi: calkantiKaynagi,
        CALKANTI_KAYNAK_SURUMU: CALKANTI_KAYNAK_SURUMU,
        clear: clear,
        detectMotorType: detectMotorType,
        STORAGE_KEY: STORAGE_KEY
    };
})();
