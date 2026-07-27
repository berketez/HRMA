# v2.6.2 — KALAN İŞ (2026-07-25 02:00 checkpoint, Berke mola verdi)

Çalışma ağacı KOMMİTLENMEDİ. Aşağısı **diskteki ölçülmüş** gerçeğe göre
(tahmin değil: grep + import + pytest ile doğrulandı).

---

## Bu oturumda BİTEN

### D-engines (kod tarafı)
| Dosya | Ham uyarı kaldı | Durum |
|---|---|---|
| `cycle_power_balance.py` | **0** | TAM (20 nokta dönüştürüldü — önceki not "3 leak" diyordu, gerçekte 20'ydi) |
| `solid_rocket_engine.py` | **0** | TAM (ajan bitirdi, `_tr` kalıntısı da yok) |
| `injector_design.py` | **0** | Uyarılar tam; **4 `_tr` çıktı alanı kaldı** (aşağıda) |
| `liquid_rocket_engine.py` | **27** | YARIM — en büyük kalan iş |
| `validation_system.py` | 0 | TAM (önceki oturum) |
| `hrma/analysis/*` (4 dosya) | 0 | TAM (önceki oturum, 55 kod) |

### Güvenlik + performans denetimi (YENİ — bu oturumda eklendi)
- `scratchpad/security_audit_v262.md` — **19 bulgu** (2 KRİTİK, 4 YÜKSEK,
  7 ORTA, 5 DÜŞÜK), 12'si ampirik sınandı.
- `scratchpad/perf_audit_v262.md` — **12 ölçülmüş bulgu** + profiller
  (`scratchpad/prof_*.out`).

### Uygulanan düzeltmeler
- `hrma/utils/input_guard.py` (**YENİ**): `InputError`, `num`, `integer`,
  `choice`, `text`, `safe_name`. `0` ile "verilmedi" ayrımı korunur.
- **K-1 kısmen kapatıldı:** `export/step_export.py` + `export/drawing_generator.py`
  artık `safe_name()` kullanıyor (mutlak yol / `..` geçemez).
  → app.py tarafındaki ZIP arşiv adı HENÜZ kapatılmadı (aşağıda).

---

## KALAN İŞ

### 1. liquid_rocket_engine.py — 27 ham uyarı (EN BÜYÜK KALEM)
Satırlar (ilk 12): 501, 505, 509, 522, 575, 734, 737, 798, 833, 869, 980, 994.
Tam liste için:
```bash
python3 -c "
import re
src=open('hrma/engines/liquid_rocket_engine.py').read().split('\n')
for i,l in enumerate(src):
    if re.search(r'_warn\(f?[\"\x27]',l):
        blk='\n'.join(src[i:i+4])
        if '_w(' not in blk: print(i+1, l.strip()[:90])
"
```
**DİKKAT — sessiz bozulma riski:** `_warn` imzası `(self, code,
severity='warning', **params)` olarak DEĞİŞTİ (satır 470). Eski
`self._warn("bir metin")` çağrıları **çökmüyor** ama metni `code`
alanına koyuyor → frontend `TF()` eşleşme bulamaz, kullanıcı ham metin
görür. Yani bu 27 nokta "çalışıyor gibi" görünüp yanlış çıktı üretir.
- Ayrıca `:3548-3590` civarı `print("Uyarı...")` anomalileri hâlâ duruyor
  (terminale basılıyor, kullanıcı arayüzde göremiyor) → `_warn`'a taşınmalı.

### 2. injector_design.py — 4 `_tr` çıktı alanı
| Satır | Alan | Not |
|---|---|---|
| 914 | `stability.acoustic_note_tr` | gaz-gaz dalı; sıvı dalındaki eşi `acoustic_note` olarak zaten dönüştürüldü |
| 957 | `pattern.description_tr` | gaz-gaz `desc` ham Türkçe f-string |
| 967 | `atomization.note_tr` | gaz-gaz SMD notu |
| 1398 | `pattern.description_tr` | ana dal `desc` — 7 ayrı dalda kuruluyor (triplet/like/pintle×2/swirl/doublet/showerhead), her biri kendi `{code, params}`'ına çevrilmeli |

### 3. Katalog dosyaları YAZILMADI (Dalga 2'nin girdisi)
Ajanlar kesilmeden önce yazamadı. `docs/v262_specs/D_codes_analysis.md`
formatında gerekli:
- `D_codes_engines.md` — injector (25+11 kod) + solid + liquid + cycle (22 kod)
  → `| code | severity | params | EN | TR |` tablosu.
Kodları koddan çıkarmak için:
```bash
grep -ohE "'warn\.(injector|solid|liquid|cycle)\.[a-z0-9_]+'" hrma/engines/*.py | tr -d "'" | sort -u
```

### 4. KIRIK TESTLER (6 adet — hepsi eski anahtar arıyor, kod doğru)
```
tests/test_injector_design.py::TestMotorPaths::test_contract_keys_present   ('warnings_tr' arıyor)
tests/test_injector_design.py::TestStability::test_chug_guard_low_dp
tests/test_injector_design.py::TestDoublet::test_doublet_momentum_and_rupe
tests/test_injector_design.py::TestOrificePlan::test_orifice_constraints
tests/test_injector_design.py::TestSwirl::test_swirl_unreachable_theta_falls_back
tests/test_export_real_data.py::TestInjectorSingleSource::test_drawing_pdf_uses_solver_injector
```
`python3 -m pytest tests/ -k injector -q` → **6 failed, 131 passed** (39 s).
Bunlar `{code}`-assert'ine çevrilmeli. Solid/liquid testleri henüz koşulmadı.

### 5. GÜVENLİK — kalan düzeltmeler (rapor: `scratchpad/security_audit_v262.md`)
- **K-1 kalanı:** `app.py:2611, 2683, 2687, 2693, 2713` — ZIP arşiv adı hâlâ
  ham `motor_name` (ürettiğimiz ZIP zip-slip taşıyabilir). `safe_name()` uygula.
- **K-2 (KRİTİK, HENÜZ YAPILMADI):** `app.py:113` `CORS(app)` tamamen açık.
  Tarayıcıdaki herhangi bir sayfa localhost API'sini sürüp yanıtı okuyabiliyor
  (ampirik kanıt raporda). Satırı kaldır + `before_request` same-origin süzgeci.
- **Y-1:** `six_dof_trajectory.py:544,574` adım/duvar-saati bütçesi yok →
  `fin_count=1e6` ile 90 s+ donma. Desen zaten var:
  `hybrid_rocket_engine.py:29 MAX_BURN_INTEGRATION_STEPS`.
- **Y-2:** `app.py:1079` `t_max` sınırsız → kaçış yörüngesinde bitmeyen entegrasyon.
- **Y-3:** `MAX_CONTENT_LENGTH` yok; `/api/validation/upload-csv` gövde sınırsız.
- **Y-4:** `/api/correlation-report` senkron + eşzamanlılık kilidi yok.
- **O-1:** `hybrid_rocket_engine.py:72-73` `thrust=0` → sessizce 1000 N,
  `burn_time=0` → 10 s, HTTP 200. (`input_guard.num` ile kapanır.)
- **O-3:** `/api/quick-geometry` motor doğrulayıcısını hiç çağırmıyor (1e6 bar kabul).
- **O-7:** `tile_cache.py` **hiçbir rotaya bağlı değil** — ön yüz `/api/tile/...`
  çağırıyor, 404 alacak. (Zaten entegrasyon işinde vardı.)
- Kalan O/D bulguları raporda; sonunda öncelik sıralı 10 maddelik liste var.

### 6. PERFORMANS — kalan düzeltmeler (rapor: `scratchpad/perf_audit_v262.md`)
- **P-1:** `cea_bridge.py:127` `lru_cache(maxsize=512)` → tahliye çöplüğü.
  A/B ölçüm: korelasyon koşusu **121.5 s → 94.4 s** (maxsize=100000). Tek satır.
- **P-2:** `CombustionAnalyzer()` kurucusu her seferinde `ct.Solution('gri30.yaml')`
  ayrıştırıyor: **25.9 ms → 1.19 ms (21x)**. `/parametric-analysis` süresinin %61'i.
  Bit-aynılık ölçüldü: 4 durumda T/X/MW/cp farkı **tam 0.0**.
- **P-3:** `/api/database-status` her çağrıda canlı NIST isteği, `timeout=10` →
  ağ kesikse **tam 10.00 s asılma**. `advanced.html:3562` sayfa açılışında tetikliyor.
- **P-4:** `/api/correlation-report` soğuk koşu **123 s** (docstring "~15-25 s"
  diyor, DB 136→209 kayda çıkınca güncellenmemiş).
- **UYARI:** `analyze_combustion`'ın mevcut `memoize=True` yolu anahtarı
  YUVARLIYOR (O/F@0.01, Pc@0.1) — yeni memo o yolu KULLANMAMALI.

### 7. ENTEGRASYON (paylaşımlı dosyalar, tek elden)
- **app.py:** `/api/flight-vehicle` (A1), 3 × `/api/tile/...` (A2),
  `latitude_deg` passthrough (B1, :1063-1078), B5 `float(thrust/burn_time)`,
  C2 `experiment_db` memoize.
- **launch_site.html:** araç paneli + sabit demo söküm (:391-398) +
  `latitude_deg: la`; GIBS attribution + "önbelleği temizle"; A3 uçuş-yok
  kontrol disable + ipucu; B4 "range" etiketi.
- **i18n_launch_site.js:** A1/A2/A3 anahtarları + B1 2 string
  (`site.groundTrackLabel` / `site.earthRotNote` — spec `B1_coriolis.md`'de hazır).

### 8. DALGA 2 — frontend
- **D-frontend:** `app.js:982-998`, `liquid.html:4488-4496`,
  `advanced.html:2817-2845`, `injector_panel.js:376,385`, `safety_panel.js:300`,
  `thermal_panel.js:424`, `structural_panel.js:269`, `uzaytek.html:1086`,
  `simple.html:392` → ham render'ı `TF(code, params)`'e çevir.
  AYRICA `advanced/solid/liquid.html`'e `flight_handoff.js` `<script>` + çağrı.
- **i18n-dicts:** ~200 `{code}` → TR+EN, `i18n_common.js` / `i18n_pages.js`.
  Backend kodlarıyla BİREBİR eşleşmeli.
- **injector_panel.js DİKKAT:** `warnings_tr`/`assumptions_tr` →
  `warnings`/`assumptions`; `feed_coupling_warning_tr` → `feed_coupling_note`;
  `acoustic_note_tr` → `acoustic_note` (alan adları değişti, panel kırılır).

### 9. DOĞRULAMA
- Tam pytest (2700+). **Şu an app ara durumda:** backend `{code}` dict
  döndürüyor, frontend henüz `TF()` yapmıyor → uyarılar `[object Object]`
  görünür. Tam yeşil ancak Dalga 2 + entegrasyon sonrası.
- i18n parity bekçisini `{code}` anahtarlarını kapsayacak şekilde genişlet.
- Playwright duman testi: uyarılar HER İKİ dilde doğru render.

### 10. README KAPSAMLI YENİLEME (Berke isteği 2026-07-25)
Programı tanıtan, **resimli / simülasyonlu**, kapsamlı bir README.
"Gören direkt 'bu ciddi proje' desin" hedefi.
- **Mevcut iki "key formül" bloğu KALDIRILACAK** (Berke: "saçma olmuş").
- Ekran görüntüleri + 3D Dünya / uçuş animasyonu görselleri kullanılabilir.

### 11. DOKÜMAN SENKRONU (sürüm hijyeni — `V2.6.2_PLAN.md`)
`__init__.py` 2.6.1→**2.6.2**, `changelog.json` (notes_en+tr), README,
`USER_MANUAL` (2.5.5→2.6.2 + launch-site v2), kılavuz PDF'leri TR+EN
(YENİ launch-site ekranları), `VALIDATION_STATUS`,
`packaging/release_notes_v2.6.2.md`.

### 12. DERLEME + YAYIN
`restore_build_inputs` → `build_mac_app` + `build_dmg` → `build_win_payload`
+ `makensis` exe. **Berke bu sürümü yayınlamayı onayladı** (2026-07-25).

---

## Bu oturumun dersi (ÖNEMLİ)
**Mekanik toplu-dönüşüm işi ajana verilmemeli.** 3 dev ajanı 4 saatte
~90 noktanın ~52'sini yaptı; ana modelde grep + toplu düzenleme ile
`cycle_power_balance.py`'nin 20 noktası **15 dakikada** bitti (~8x fark).
Sebep: ajan her düzenleme öncesi dev dosyayı parça parça yeniden okuyor ve
aralarda pytest koşuyor (bu projede CEA yüzünden tek koşu dakikalar sürüyor).
Ajanlar 00:48'de kesildi; kesme hasar vermedi (4 dosya da sözdizimi sağlam),
ama injector'da yarım kalan yeniden adlandırma bir **NameError** bırakmıştı
(`warnings_tr` döndürülüyordu, değişken artık yoktu) — elle kapatıldı.
Ajan işi yarıda kesilirse **çıktı sözleşmesi mutlaka elle doğrulanmalı**.
