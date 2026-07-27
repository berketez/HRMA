# A1 (araç köprüsü) + A3 (UI onarımı) spec (ARGE, kod-teyitli)

## Mimari bulgu
sixdof_panel.js motor sayfalarında A1'i ZATEN çözmüş (airframe formu + thrustProvider + deriveMassProps :430-449). launch_site.html bunu sabit demoyla yeniden icat ediyor (:391-398). A1 = deseni launch-site'a taşı. /launch-site AYRI sayfa (motor formu/currentResults YOK) → motor oraya taşınmalı. 3 thrustProvider FARKLI alan adları → **tek Python normalize** (rule#11).

## Tek normalize kaynağı: YENİ hrma/analysis/flight_vehicle.py::normalize(motor_type, results)->dict
Çıktı şeması: `{motor_type, motor_name, thrust_curve:{time[],thrust[]}|null, thrust, burn_time, propellant_mass, engine_inert_mass, engine_od_m, engine_length_m, source}`.
Motor-tipi alan eşlemesi (gerçek anahtarlar):
| Alan | hybrid | solid | liquid |
|---|---|---|---|
| thrust_curve | TransientPanel (yoksa null) | results.thrust_curve (top-level) | null |
| thrust/burn_time | motor.thrust/motor.burn_time (hybrid_rocket_engine.py:997,1041) | average_thrust/burn_time | thrust/burn_time (liquid:3625,3702) |
| propellant_mass | motor.propellant_mass_total (:1032) | propellant_mass | mdot_total*burn_time / design_summary.propellant_mass_kg (:3770) |
| engine_inert_mass | design_summary.key_dimensions.dry_mass_estimate_kg (:1242, =0.25·prop **TAHMİN**, "tahmin" etiketle) | design_summary.masses.dry_mass_kg | feed-system total_mass (:1225) |
| engine_od_m | motor.chamber_diameter (:1013) | cad_design.case_design.outer_diameter/1000 | chamber_diameter (soft) |
| engine_length_m | design_summary...total_motor_length_mm/1000 (:1240) | grain+nozul | total_length/1000 (:2765) |

## İki kaynak, tek şema
(a) **Oturum köprüsü (birincil, localStorage):** YENİ flight_handoff.js — motor sayfası hesap başarısında (currentResults set: app.js:224, solid.html:2753, liquid.html:2113) `POST /api/flight-vehicle {source:'results',motor_type,results}` (recompute YOK, normalize) → dönen aracı localStorage['hrma.flight.lastVehicle']'e (motor_name+timestamp). launch_site okur. WKWebView'de localStorage çalışıyor (sixdof_panel.js:799).
(b) **.hrma projesinden (recompute):** launch_site "Kayıtlı projeden" → GET /api/projects → seçimde POST /api/flight-vehicle {source:'project',name}. Backend: .hrma yükle→inputs.fields'i ilgili /calculate|_solid|_liquid'e ver→**yeniden hesapla**→normalize. NEDEN recompute: .hrma sadece girdi+results_summary saklıyor (projects.py:61-65), thrust_curve/propellant_mass YOK. Yükleniyor göstergesi.
(c) **Örnek araç:** mevcut demo (kanatlı, uçabilir) korunur ama VARSAYILAN DEĞİL, source:'example' rozetiyle.

## Airframe paneli (launch_site.html)
İki görsel sınıf:
- **Motor-türevi + KİLİTLİ** (readonly, opacity 0.65, kilit ikonu, "motordan"): itki(eğri/sabit), propellant_mass, engine_inert_mass (hybrid'de "tahmin ~0.25·prop" notu), engine_length/od (bilgi).
- **Kullanıcı** (varsayılan+"?"): body_diameter(prefill=engine_od, min=engine_od guard), body_length(default=max(2.0,engine_length+1.0)), nose_length(0.40)/nose_type(ogive), **kanatlar** (fin_count4,root0.20,tip0.10,span0.11,sweep0.08,position1.80 — stabil araç verir, "varsayılan kanat" etiketi), airframe_dry_mass (motor atıl HARİÇ), cd0(0.45), launch_elevation(84)/azimuth(90)/rail(5), wind.
- **latitude_deg: la** (B1'den — #ls-lat'tan zaten var :387) body'ye ekle.
- **ÇİFT-SAYIM (TUZAK2):** çözücüye dry_mass=airframe_dry_mass+engine_inert_mass; propellant_mass=engine.propellant_mass ayrı. engine_inert_mass ATIL (propelan hariç). Birim testi.
- CG: kullanıcıdan istenmez, backend fallback (0.55L/0.50L, six_dof:277-278) "CG tahmini" notuyla.
- Etiket: "Uçurulan araç: <motor_name> (<kaynak>)" — yeni i18n site.flyingVehicle.

## Kanatsız/kararsız dürüst ele alış (TUZAK1)
- Kanat default'ları → gerçek motor varsayılan STABİL. Kullanıcı sıfırlarsa kararsız.
- Solve SONRASI kapı (client Barrowman DUPLİKE ETME): /api/six-dof-analysis yanıtı zaten summary.static_margin_full, summary.stable, summary.end_reason döndürüyor (six_dof:531-534, app.py:1094-1098). end_reason==='tumble_detected' VEYA static_margin_full<1.0 VEYA stable===false → uyarı banner + oynatımı ETKİNLEŞTİRME.
- Airframe hiç tanımsız (fin_span/root 0) → Fly ön-kontrolle engelle+ipucu.

## .hrma airframe round-trip (projects.py)
- _ALLOWED_INPUT_KEYS (:65) += 'airframe'. Yeni _validate_airframe (düz skaler sözlük, _validate_fields gibi). validate_payload (:276 sonrası) if 'airframe' in inputs.
- Okuma: /api/flight-vehicle {source:'project'} yanıtına airframe ekle. Yazma: merge-save (load doc→doc.inputs.airframe=panel→save overwrite).

## A3 — kontrol denetimi + resolve
- Uçuş-gerektiren kontroller (ls-playpause :422, ls-reset :423, ls-exagg :426, ls-follow :429) HTML'de disabled BAŞLAT; setFlightPath başarısında (:411-412) disabled=false; yeni saha/araç seçilince yeniden disable. ls-view-globe/site her zaman etkin. İpucu: "Kontroller bir uçuş çözülünce etkinleşir" (site.controlsNeedFlight).
- **presets/apply/resolve KIRIK DEĞİL** (teyit). resolve (:355-383) endpoint VAR (app.py:1108); ama hata metni yanıltıcı: ":380-381 'resolver endpoint is not wired yet'" → "Saha çözümü başarısız (çevrimdışı olabilir)" (site.resolveUnavailable metni). Küçük düzeltme.
- B4: "range" (:466 globe.js) apoje yatay sapması, iniş menzili değil → etiket "apoje yatay sapması" veya not.

## Dosya sahipliği
**A1 ajanının YAZACAĞI (backend/motor-sayfaları — launch_site.html HARİÇ, izole):**
- hrma/analysis/flight_vehicle.py (yeni normalize)
- hrma/utils/projects.py (airframe key+validator)
- hrma/static/js/flight_handoff.js (yeni)
NOT: advanced.html/solid.html/liquid.html'e handoff <script>+1 çağrı GEREKİR ama bu 3 dosyayı D-frontend de değiştiriyor → ÇAKIŞMA. Çözüm: bu 3 html'e handoff script eklemeyi D-frontend ajanı yapar (tek sahip). A1 ajanı flight_handoff.js'i yazar, D-frontend script tag'ini ekler.
**launch_site.html + i18n_launch_site.js (A1 panel + A3 + A2 attribution + B1 string) → ANA ENTEGRATÖR tek elden (paylaşımlı dosya).**
**app.py /api/flight-vehicle route → ANA ENTEGRATÖR.**
