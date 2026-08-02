# Faz 4 — Codex raporu teyidi (birleştirilmiş bulgu defteri)

**Taban:** HEAD `a7ff1e7` · **Ölçüm tarihi:** 2 Ağustos 2026
**Kaynak rapor:** `~/Desktop/HRMA_Profesyonel_Kullanim_Eksikleri_ve_Yol_Haritasi.md`
(Revizyon 3, `d908ae7` = v2.6.25 tabanlı, 7910 satır, 1366 kutu)

**Yöntem:** 7 salt-okunur denetim ajanı + ana Claude'un kendi ölçümü. Her hüküm
`dosya:satır` alıntısı veya çalıştırılmış ölçüm ile kanıtlandı. Hiçbir ajan
depoya yazmadı (`git status --porcelain` → 0, ölçüm öncesi ve sonrası).

**Önemli bağlam:** Rapor `d908ae7`'i denetledi. O tarihten beri 120 dosya değişti,
+30837 satır eklendi (Faz 0-3). Bu yüzden raporun bazı bulguları **artık yanlış**,
bazıları **daha kötü**, ve rapor bazı yerlerde **kodun gerisinde**.

---

## 0. Toplu sonuç

| Küme | Kapalı | Kısmi | Açık |
|---|---:|---:|---:|
| §56 P0 stop-ship (10) | 1 | 5 | 4 |
| §55 kısmi maddeler (8) | 1 | 4 | 3 |
| §57 + §29 fizik/sayısal (20) | 2 | 9 | 9 |
| §58 + §35 güvenlik (17) | 6 | 5 | 6 |
| §59 + §60 V&V/yönetişim | 3 | 4 | 8 |
| §26 + §27 export/veri (16) | 0 | 9 | 6 |
| §28 modül fiziği (20) | 1,5 | 12,5 (+3 beyanlı) | 3 |
| §17 + §43 iddia dili (6) | 0 | 0 | 6 |

**Baskın desen — kapı sorunu, fizik sorunu değil.** Bulguların büyük çoğunluğunda
doğru sayı hesaplanmış, doğru bayrak yazılmış, **kimse bayrağı okumamış**.
Faz 1-3'te beyan kanallarını kurduk; karar kapılarını kurmadık.

---

## A. Kullanıcıya doğrudan yanlış mühendislik veren kalemler

Bunlar Faz 1-3'te kapattığımız sınıfın hayatta kalan kollarıdır.

| # | Bulgu | Kanıt | Efor |
|---|---|---|---|
| A1 | **STL metre, README "millimetres"** — 1000× | `app.py:3441,3472` sabit metin; aynı ZIP'te STEP bbox `1069,62 mm`, STL bbox `1,0696` | BASİT |
| A2 | **DXF `$INSUNITS = 6` (metre)**, geometri mm | `drawing_generator.py:296` `ezdxf.new(setup=True)` varsayılanı; `grep -rn INSUNITS` → boş | BASİT |
| A3 | **Bilinmeyen yakıt çifti uydurma performans veriyor** | `{fuel:'zirvaaa',ox:'gizemli'}` → 200, `OPTIMIZED`, Isp 285/320 s, c* 1650 — `liquid_rocket_engine.py:1934-1940` literalleri | ORTA |
| A4 | **NaN geometri → HTTP 200 + katı cisim** | `/api/export-step`, `-dxf`, `-drawings-pdf`, `-complete-zip` hepsi 200; OCC geri okuma: 308×109 mm, 5,179e5 mm³ | ORTA |
| A5 | **Nozul uzunluğu bell'de −42%** | `motor_geometry.py:74-86` çıktıda `nozzle_length` yok → `nozzle_design.py:1010-1012` bell **boğaz** açısını konik yarı açı sanıyor. bell_80: 89,57 → 51,96 mm | BASİT |
| A6 | **6DOF enine atalet %2,91 eksik** | `six_dof_trajectory.py:769` paralel eksen terimi yok; `:751-752` docstring'i terimi ve "%3.0 EKSİK" uyarısını yazıyor. Aritmetik doğrulandı: `x_cg=0,55L` → `0,0025mL²/0,0833mL² = %3,0` | BASİT |
| A7 | **Cache anahtarı fiziksel ayrımı yutuyor** | `Pc=20,04 bar` isteği `Pc=20,00` sonucunu döndürüyor, c* bit-aynı | ORTA |
| A8 | **Katı motor cidarı imalata farklı gidiyor** | `step_export.py:99` katıda olmayan `chamber_analysis`'i arıyor (katı `case_analysis` yayımlıyor) → `0,045×D_ch` yedeği. Analiz 124,0 mm, STEP 109,0 mm | BASİT |
| A9 | **Parametrik tarama başarısızlığı gizliyor** | 5 nokta istendi, 4 döndü, `status:'success'`, `fail*` alanı yok (`app.py:2730-2733`). Negatif O/F = −2,0 → Isp 204,77 s, `motor_validator` çağrılmıyor | BASİT |
| A10 | **`/api/export-cad` eski dosya sunuyor** | `app.py:3573` link üretir, `export_stl_files` `mkdtemp`'e yazar, uç `cwd/cad_exports`'tan okur. sha256 farklı, mtime 31 Temmuz | BASİT |
| A11 | **Tank: üç ayrı geometri** | Analiz düz kapaklı silindir / STEP silindir+2 tam küre, içi dolu / FreeCAD iki ucu açık boru. Boy %40, hacim %26,7 fark | ORTA |
| A12 | **OpenRocket `.eng` uydurma araç** | Boş `motor_data` → `M0-... 0.0 500.0 P 1.000 1.000` (çap sıfır). Uydurma 5 kg araçtan 258 km apoje; `rocket_parameters_source` alanı yok | BASİT |

---

## B. Bayrak yazılıyor, kimse okumuyor

| # | Bulgu | Kanıt | Efor |
|---|---|---|---|
| B1 | `_defaults_used` / `_fallback_used` **14 append, 0 okuma, 0 yayım** | `hybrid_rocket_engine.py:2457` ve `liquid_rocket_engine.py:4492` sabit `'OPTIMIZED'`; `:223-227` yorumu "status bu bayrağı okur" diyor | BASİT (3 satır) |
| B2 | Yakınsamayan çözüm performans + CAD üretiyor | `n=0,9`: `convergence_achieved=False`, artık 0,0167 / tol 1e-6, `termination_reason=pressure_collapse` → yine `CALCULATED`, Isp 3,8 s, `cad_design` 9 anahtar dolu. Bayrak JS/HTML'de hiç geçmiyor | ORTA |
| B3 | Totoloji bayrağı ile hüküm aynı yanıtta | `POST /analyze_structural_safety -d '{}'` → `safety_factor_is_tautological=True` **ve** `status:ACCEPTABLE`, `risk_level:LOW`, `peak_wall_temperature_K:300.0` | BASİT |
| B4 | Yapısal uç kendi kalınlığını boyutlandırıp SAFE diyor | `wall_thickness=0,001` gönderildi, modül 5,887 mm kullandı. `app.py:4548` `actual_wall_thickness`/`design_safety_factor` argümanlarını geçirmiyor — hibrit yolu (`hybrid_rocket_engine.py:1380-1386`) geçiriyor | BASİT |
| B5 | 27 SciPy çözücü çağrısının 1'inde başarı denetimi | `grep -c "success" six_dof_trajectory.py` → **0**. `kinetic_analysis.py:352-355` çıplak `except:` → `return 2.0` Mach | ORTA |

**Referans çözüm deponun içinde:** `/analyze_safety` ucu doğru yapıyor
(422 + `defaults_applied`). O 14 satırın yapısal ve OpenRocket uçlarına
kopyalanması B3+A12'yi birlikte kapatır.

---

## C. İddia dili ve standart atfı (§17, §43 — ana Claude ölçümü)

| # | Bulgu | Kanıt | Efor |
|---|---|---|---|
| C1 | PDF teknik eki hâlâ "NASA-standard methodologies" basıyor | `pdf_generator.py:992`; `:78-90` yorumu düzeltmenin yapıldığını söylüyor ama yalnız yönetici özetine uygulanmış (`:368-382`). `:276` teknik eki çağırıyor, ölü kod değil | BASİT |
| C2 | **NASA-STD-5012 yanlış konu + yanlış başlık** | Gerçek adı *Strength and Life Assessment Requirements for Liquid-Fueled Space Propulsion System Engines* (Rev. B, 2016). Kod "Pressure Vessels & Pressurized Systems" diyor ve **lülede Mach-alan bağıntısının ve basınç düşümünün** kaynağı olarak gösteriyor. 9 yer: `app.py:5191,5229`, `formulas.html:1186,1196,1240`, `i18n_formulas.js` EN+TR, `performance_panel.js:7`, `pdf_generator.py:996` | BASİT |
| C3 | NASA SP-8124 yanlış başlık | Gerçek adı *Liquid Rocket Engine Self-Cooled Combustion Chambers* (1977). Kod "Thermal Design Criteria" diyor | BASİT |
| C4 | "NASA-grade accurate" hükmü | `nasa_realtime_validator.py:284-292` — tek yüzde hatasından üç yasak ifade: `NASA-grade`, `Good accuracy for engineering purposes`, `Acceptable for preliminary design` | BASİT |
| C5 | `formulas.html` §14 iddiası | `:1164-1165` "Professional-grade analysis methods based on **validated** NASA standards" | BASİT |

**Ölçülmeyen:** Kodda 40 farklı standart atfı var (`NASA SP-8089` ×45,
`ISO 898-1` ×34, `NASA SP-125` ×24, `AIAA S-080` ×18 …). Kontrol edilen 3
başlığın 3'ü de yanlış çıktı; kalan 37'nin doğruluğu **ÖLÇÜLMEDİ**.

---

## D. Güvenlik ve veri bütünlüğü

| # | Bulgu | Kanıt | Efor |
|---|---|---|---|
| D1 | **Eşzamanlı export'lar birbirinin dosyasını veriyor** | 8 eşzamanlı `/api/export-dxf`: A(Ø100) isteyen 4 istemcinin hiçbiri kendi dosyasını almadı; bir istemci 32796 baytlık **kesik DXF**'i HTTP 200 ile aldı. Sebep `drawing_generator.py:165` gün, `step_export.py:84` saniye çözünürlüklü ad + `exist_ok=True`. Üretimde `launcher.py:619` waitress `threads=8` | ORTA |
| D2 | **Pickle önbelleği kod çalıştırıyor** | Kurcalanmış `.pkl` ile `/bin/sh` çalıştırıldı (`uid=501`). `web_propellant_api.py:88`; dizin tahmin edilebilir, checksum/şema yok. Ayrıca 10 yıllık bayat pickle `'NIST API (Live)'` etiketiyle kabul edildi | ORTA |
| D3 | `offline_store` yazma yarışı | 8 süreç × 60 yazma → **413/480 kayıt kayıp (%86)**. `get()` paylaşılan mutable nesne döndürüyor. Aynı repoda `cea_bridge.py:399-402` doğru çözmüş — iki standart | ORTA |
| D4 | `.ork` XXE bekçisi UTF-16 ile atlatılıyor | `ork_import.py:55` regex ham bayta bakıyor. UTF-8 → "DTD rejected"; UTF-16 → ayrıştırıcıya ulaştı | BASİT |
| D5 | PDF uçları `safe_name` kullanmıyor + `Paragraph` kaçışsız | `app.py:5549`; `pdf_generator.py:309` kapanmamış etiketle HTTP 500 | BASİT |
| D6 | `job_runner` kapasitesiz | `job_runner.py:71` `maxsize=0`; 5000 iş reddedilmedi, iptal API'si yok | ORTA |
| D7 | Tam istek gövdesi loga ve destek paketine gidiyor | `app.py:2335,2415` → `hrma_log.txt`; `launcher.py:651` onu destek paketine koyuyor | BASİT |
| D8 | XLSX toplam bütçe yok | 23,3 MiB tek meşru istek → 26,3 s, 2,4 GB RSS. 60k sütun yakalanmadı; 200k karakter openpyxl'de sessizce 32767'ye kırpıldı | BASİT |
| D9 | `/api/export-xlsx` `safe_name` bypass | `filename='../../../../etc/passwd.xlsx'` → 200, ad Content-Disposition'a aynen giriyor (CRLF'i werkzeug kesiyor) | BASİT |
| D10 | `/tmp` birikmesi | 77 dizin / 17 MB; temizlik yok | BASİT |

---

## E. Yayın zinciri — v2.6.26'yı doğrudan ilgilendirir

| # | Bulgu | Kanıt | Efor |
|---|---|---|---|
| E1 | **v2.6.25 ikilisi temsil ettiği kaynaktan önce üretildi** | GitHub zaman damgaları (UTC): DMG+EXE `22:46:25` → commit `d908ae7` `23:23:16` → CI başladı `23:23:50` → **sürüm yayınlandı `23:30:44`** → CI yeşil `23:38:09`. İkili commit'ten **37 dk önce**, yayın CI yeşilinden **7 dk 25 sn önce** | — |
| E2 | `KAPIYI_ATLA=1` 288 satırlık kapının tamamını atlıyor | `packaging/publish_release.sh:55`; draft kısıtı, gerekçe, kayıt yok. E1'in mekanizması | BASİT |
| E3 | `.github/workflows/` altında yalnız `tests.yml` — release iş akışı yok | `ls` | ORTA |
| E4 | **`VALIDATION_STATUS.md` bayat** | Korelasyon bugün HEAD'de koşturuldu: **3 satır farklı**. Kaldırılması gereken `hybrid\|thrust\|main` satırı belgede duruyor — aynı repoda o hücrenin olmamasını sınayan test var (`test_correlation_guards.py:185`). `README.md:103` bu bloğa **"always-current"** diyor | BASİT |
| E5 | Yönetişim dosyalarının 7'si de yok | CONTRIBUTING, SECURITY, CODEOWNERS, pre-commit, lint config, CITATION — `find` ile doğrulandı. main korumasız (`gh api` → 404), tag'ler lightweight, commit'ler imzasız | BASİT |

---

## F. Bekçi testleri hatayı koruyor

Bu ayrı bir başlık hak ediyor: **üç yerde test, kusuru sözleşme olarak kilitlemiş.**

| Test | Ne yapıyor |
|---|---|
| `test_six_dof_trajectory.py:324,344` | Paralel eksen terimi olmayan **yanlış** atalet formülünü `rel=1e-12` ile kilitliyor. Doğru düzeltmeyi yapan kişi testi kırmak zorunda |
| `test_safety_honesty.py:200` | Yalnız `'conducted using NASA-standard methodologies'` dizesini arıyor; `pdf_generator.py:992`'deki `'employs NASA-standard methodologies'` yakalanmıyor |
| `test_tank_step_units.py:70` | STEP **metnindeki** `CARTESIAN_POINT` sınırlarını ölçüyor ve "800 mm" assert'i geçiyor; aynı dosyada `import_step().bounding_box()` **1100 mm** veriyor. Küreler `SPHERICAL_SURFACE` olduğu için kutupları metinde nokta olarak yazılmıyor |

Ayrıca `test_export_real_data.py:164` ve `test_correlation_runner.py:305`'te
raporun işaret ettiği **2 boş assertion** aynen duruyor; 82 atlama noktası var
ve yayın kapısında skip bütçesi yok.

---

## G. Codex'in yanıldığı yerler — kod raporun ilerisinde

Bunlar `d908ae7` sonrası kapanmış, rapor bilmiyor:

- **ZIP-slip kapalı.** `motor_name="../../EVIL"` ile üç ZIP ucu çağrıldı, 15 entry, güvensiz **0** (`app.py:3377` `is_safe_arcname`).
- **XLSX formül enjeksiyonu kapalı.** OWASP corpus gönderildi, `data_type='f'` sayısı **0**, externalLink 0, makro 0; gerçek negatif sayılar bozulmadı.
- **Host/Origin kapısı kapalı** — GET dahil (`app.py:452-457`). `Host: evil.example` → 403 `host_not_loopback`.
- **Export sanitizer** artık `None` döndürüyor, `0` değil.
- **Katı CAD kasa parametreleri** `_case_design()` ile **bit-aynı** (5 override kombinasyonunda ölçüldü) — raporun "her zaman 8 mm / AISI 4130" iddiası yanlış.
- **Safety ucu** boş istekte 422 dönüyor; sayısal failure probability kaldırılmış.
- **Global uyarı susturma tamamen kalkmış** — `np.geterr()` üçü de `'warn'`, catch-all `ignore` filtresi 0.
- **Termal↔yapısal parite gerçek.** 4/5/6 mm'de SF 2,215 → 2,733 → 3,236 monoton; ASME membran oranı 0,853 → 0,692 → 0,584; `safety_factor_is_tautological: false`.
- **Bulgu kayıt defteri var ve makinece denetleniyor.** `docs/BULGU_KAYIT_DEFTERI.md` + `tests/test_findings_registry.py` (34 test): her `test_x.py::test_y` atfının varlığı doğrulanıyor, "Açık borç" bölümünün silinmesi yasak. §59.1'in çekirdeği kurulu.
- **`PHYSICS_AUDIT.md`**'nin 106 "düzeltme gerekli" bulgusunun 106'sı kodda F-ID ile izlenebilir (38'inin adlandırılmış testi var).
- **Enjektör raporun sandığından çok ileri:** SPI + HEM + NHNE (Dyer), `discharge_coefficient(inlet, l_over_d)`, hidrolik flip, üç SMD korelasyonu, swirl çözücü, gaz-gaz koaksiyel. Gerçek eksikler dar: patternation, maldistribution, coking.
- **`cycle_power_balance.py`** 6 çevrimi kapanan güç dengesiyle çözüyor ve `liquid_rocket_engine.py:4930`'da gerçekten bağlı.
- **Kaynama 5 ayrı yerde** "NOT modelled (flagged only)" beyanlı ve riskli istasyon sayılıyor — "eksik" değil "sınırı ilan edilmiş".
- **`P0-01` artık P0 ağırlığı taşımıyor.** 11 şablon kalemin 8'i kalkmış; kalan 3'ü (`ATJ` grafit, `AISI 316` enjektör, `Ra 3.2`) `basis`/`source` alanında "bu analizde seçilmedi" beyanı taşıyor. Beyansız kalan tek yol `cad_export.py:657` `_generate_drawing_notes`.

---

## H. Raporda olmayan, ajanların bulduğu iyi fikirler

Hepsi **mevcut bir yeteneği ikinci bir yere bağlamak** — yeni kavram icadı değil.

1. **Ortak export manifesti** (`export_manifest.py`): sürüm + girdi sha256 + birim/eksen + varsayım listesi, 9 çıktının hepsine gömülü. A1/A2/A4/A10'un tamamını tek yerden yakalar.
2. **`analysis()` / `template()` etiketlemesini yayma.** `cad_export.py:527-570`'te zaten çalışıyor — sahte veri yasağının makineleşmiş hali.
3. **Birim bekçisi testi.** İki 1000× hatayı (A1, A2) bulan yöntem tam olarak buydu; proje aynı fikri çizim↔mesh için zaten uyguluyor.
4. **Yasak iddia lint'i** (rapor §43.4'ün son maddesi) + `docs/STANDART_ATIFLARI.md` kayıt defteri: numara → tam ad → revizyon → ilgili madde → hangi hesapta kullanıldı. Lint yalnız defterdeki adları kabul eder. C1-C5'i kalıcı kapatır.
5. **`geometry_hash`** — 5 tüketici zaten tek örnekleyiciyi çağırıyor, hash eklemek ucuz.
6. **Üç motora tek `input_provenance` şeması.** Hibritte `NOT_MODELLED` sayısı **sıfır**, katıda 19. Şema testi bayrağın **okunduğunu** da zorlayabilir — B kümesinin tamamının kökü.
7. **`/analyze_safety`'nin 14 satırlık kapısını** yapısal ve OpenRocket uçlarına kopyala (B3 + A12).
8. **Slosh'u tank tasarımından besle** — `g_eff` varsayılanı 9,80665, uçuşta frekans √g ile ölçekleniyor.

---

## I. Kapsam dışı (BÜYÜK — v2.6.26'da yapılmaz)

Formal SRS, çift yönlü RTM, bağımsız IV&V, QMS, iki-reviewer kuralı, TUF/Sigstore
imza altyapısı, kör holdout test kampanyası, akreditasyon, kalifikasyon.
Projenin kendi planı (`docs/V2.6.26_PLAN.md:318`) bunları zaten dışarı almış;
o karar doğru. Tank tek geometri (A11) ve updater imza zinciri de bu sınıfa yakın.

---

## J. Hüküm

Faz 1-3'te **beyan kanallarını** kurduk: `_basis`, `_source`, `_status`,
`NOT_MODELLED`, sabit sınıflandırması. Faz 4 şunu ölçtü: **kanallar dolduruluyor,
kapılar yok.** `_defaults_used`'a 14 kez yazılıyor, sıfır kez okunuyor.
`convergence_achieved=False` yazılıyor, sonuç yine `CALCULATED`.
`safety_factor_is_tautological=True` yazılıyor, aynı yanıtta `ACCEPTABLE`.

Buna ek olarak **iki tane 1000× birim hatası** (STL, DXF) ve **bir fizik hatası**
(6DOF atalet) duruyor — üçü de Faz 1-3'ün tarama yönteminin göremeyeceği
yerlerde, çünkü tarama girdi→çıktı bağlantısını ölçtü, **birimi ve mutlak
doğruluğu** değil.

Yayın zinciri ayrı bir mesele: v2.6.25 ikilisi temsil ettiği commit'ten 37 dakika
önce üretilmiş. Aynı yolla v2.6.26 çıkarılırsa aynı şey olur.
