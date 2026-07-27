# D (tam iki dillilik) + C (bug/perf) spec (ARGE denetimi)

## D — sızıntı İKİ YÖNLÜ
Bazı backend sabit TÜRKÇE (EN modda sızar), bazı sabit İNGİLİZCE (TR modda sızar). Frontend hepsini ham basıyor. ~150-220 metin, ~18 dosya. Çoğu parametreli → placeholder i18n gerekir.

### HEDEF DESEN (referans: launch_site.py:522,536 ZATEN anahtar döndürüyor 'dem_missing')
Backend formatlı-string YERİNE `{code, params, severity}` döndürsün; frontend TF(code, params) ile metni kursun. Dil tamamen frontend'e taşınır, backend dilsizleşir. Bekçi: i18n parity testi backend kod anahtarlarını da kapsasın.

### Frontend ham-render yerleri (çeviri YOK — TF()'e çevrilecek)
- app.js:982-998 displayWarnings (etiket çeviriliyor ama :996-998 mesaj `w` ham, :992 overall_status ham)
- liquid.html:4488-4496 (overall_status, critical/regular/injector/input ham)
- injector_panel.js:376,385 (warnings_tr/assumptions_tr ham)
- safety_panel.js:300-301, thermal_panel.js:424, structural_panel.js:269-270 (recommendations ham)
- app.js:388,405 (frontend'de İngilizce push — TR'de sızar)
- uzaytek.html:1086 ('Uyarılar:' TR önek), simple.html:392 ('Warnings:' EN)
- advanced.html:2817-2845 (NASA CEA mesajları innerHTML İngilizce)

### Backend TÜRKÇE üreten (→EN sızar), YÜKSEK
- **validation_system.py (TÜMÜ Türkçe, en görünür — ekrandaki "UYARILAR MEVCUT" kaynağı):** :57-58,64-65,71,77,90,92,102,104,110,125,131,133,138,144,168-175,181,183,189,191 uyarılar; :212,214,216 overall_status ("KRITIK SORUNLAR MEVCUT"/"UYARILAR MEVCUT"/"TUM PARAMETRELER NORMAL"). ⚠️ :207-208 'KRITIK'/'UYARI' string'i FİLTRE anahtarı olarak da kullanılıyor → kod+severity ayır, filtreyi bozma.
- injector_design.py: warnings_tr+assumptions_tr (~32, :627,675,733,742,858,1300...), hata :985,1058. Değişken adı bile _tr.
- solid_rocket_engine.py hata: :2309,4053,4055,4064,4105,4123.
- app.py jsonify hata: :1019,1940,2636,2640.

### Backend İNGİLİZCE üreten (→TR sızar), YÜKSEK
- liquid_rocket_engine.py _warn() (~40, :488,492,495...) → input_warnings.
- solid_rocket_engine.py design_warnings (:556,1082-1087,1109,1120,1175,1202,1210).
- cycle_power_balance.py sol.warnings (~23, :290,300,535,545,562,608...).
- safety_analysis.py (:1132-1145,1227-1253,1348-1423 ~22) → safety_panel.
- heat_transfer_analysis.py (:1264-1268,1337-1361 ~19) → thermal_panel.
- structural_analysis.py (:978-986 ~8) → structural_panel.
- kinetic_analysis.py (:770-892 ~12).

### Efor: ~150-220 metin, ~12 backend + ~6 frontend dosya. Parametreli → TF params.
### Kapsam: Berke "hepsini, sırayla" — TAM refactor (PDF/rapor dahil), bekçi testiyle kilitle.

## C — GERÇEK BUGLAR
- B1(audit): butonlar uçuşsuz ölü = A3 kapsamı.
- B2: demo araç = A1 kapsamı.
- B3: six_dof:257-264 boş/tek-nokta thrust_curve → IndexError→500. Doğrulama→ValueError→400. (B1 ajanı, six_dof dosyasında)
- B4: globe.js:466 "range" apoje yatay sapması, iniş değil → etiket düzelt. (ANA/launch_site)
- B5: app.py:1068-1069 thrust/burn_time float'lanmadan → savunma float(). (ANA/app.py)
- Not: liquid:3548-3590, solid:4084-4125 print("Uyarı:") sadece stdout, kullanıcı görmüyor → design_warnings/input_warnings'e taşınırsa hem görünür hem i18n'e girer (D ile birlikte).

## C — PERFORMANS (büyük kazanımlar ZATEN alınmış: cea_bridge lru, DEM cache, cycle _CEA_CACHE, regen _PSEUDOCRITICAL_CACHE)
- C1: six_dof _mass_at (:319-322) O(N) trapz per türev-değeri. cumtrapz önhesap+interp. BİT-AYNI. A1 ~300-nokta eğri bağlanınca değerli. (B1 ajanı, six_dof)
- C2: experiment_db.load_records() (:429) cache'siz; app.py:5338 cache-kontrolünden ÖNCE çağrılıyor → her correlation isteğinde ~200 dosya parse. Dizin mtime anahtarıyla memoize. BİT-AYNI.
- C3/C4: NEGLIGIBLE (ISA_LAYERS tarama, per-frame clone) — DOKUNMA (erken-optimizasyon).
- İLKE: performans için doğruluk feda EDİLMEZ, çıktı bit-aynı.

## Dosya sahipliği (D)
- **D-backend-engines ajanı:** validation_system.py, injector_design.py, cycle_power_balance.py, solid_rocket_engine.py, liquid_rocket_engine.py → {code,params,severity}.
- **D-backend-analysis ajanı:** safety_analysis.py, heat_transfer_analysis.py, structural_analysis.py, kinetic_analysis.py → {code,params,severity}.
- **D-frontend ajanı:** app.js, liquid.html, advanced.html, solid.html, injector_panel.js, safety_panel.js, thermal_panel.js, structural_panel.js, uzaytek.html, simple.html → ham-render'ı TF(code,params)'e çevir + advanced/solid/liquid.html'e A1 handoff <script> ekle (tek sahip).
- **i18n sözlükleri (i18n_common.js/i18n_pages.js): yeni ~150-220 kod→metin TR+EN → ANA ENTEGRATÖR/ayrı ajan, backend {code} anahtarlarıyla eşleşmeli.**
- İKİ D-backend ajanı AYNI {code} adlandırma sözleşmesini kullanmalı (şema: `warn.<subsystem>.<slug>`; params dict).
