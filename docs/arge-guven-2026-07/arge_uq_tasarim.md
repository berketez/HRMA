# HRMA v2.5.0 — Belirsizlik Nicelemesi (UQ) Katmanı Mimari Tasarımı

ARGE raporu — 2026-07-17. Kod DEĞİŞTİRİLMEDİ; tüm ölçümler read-only + scratchpad
üzerinden yapıldı. Hedef: NASA/SpaceX mühendisinin ön tasarım aracında beklediği
"nokta tahmin yerine güven aralığı" yeteneği.

---

## 1. Yönetici özeti

- HRMA'da UQ için gereken altyapının ÇOĞU ZATEN VAR: katı motorda çalışan bir
  `run_monte_carlo` (seed'li, P5/P95'li), asenkron `job_runner` + `GET /api/jobs/<id>`
  polling sözleşmesi, üç kademeli fidelity kalıbı (fast/engineering/high_fidelity),
  `eta_c_star` parametresi ve panel JS kalıbı. Tasarım bu kalıpları GENELLEŞTİRİR,
  sıfırdan icat etmez.
- Ölçülen tek-hesap süreleri (M-serisi Mac, 20 çağrı ortalaması): katı 3.2 ms,
  sıvı 0.4 ms (ağ çağrısı paylaşılırsa; paylaşılmazsa 659 ms!), hibrit 1037 ms.
  Hibritin 715 ms'si danışma amaçlı `find_optimum_of_ratio` araması, kalanının
  çoğu denge çözümleri. İki ucuz hızlandırmayla (opt-OF atlama + denge çözümü
  memoizasyonu) hibrit örnek maliyeti ÖLÇÜLMÜŞ 91-185 ms'ye iner. MC bütçeleri
  bu ölçümlere dayanır: hibrit Fast 200 (~20 s) / Engineering 1000 (~1.5-3 dk) /
  High-Fidelity 3000 (~9-14 dk, job_runner arkasında).
- Örnekleme: Latin Hypercube, `scipy.stats.qmc` ile (scipy 1.13.1 kurulu,
  requirements `scipy>=1.11` — qmc 1.7'den beri mevcut). YENİ BAĞIMLILIK YOK,
  numpy<2 pini etkilenmez.
- Duyarlılık: Spearman sıra korelasyonu (MC örneklerinden bedava) + tornado.
  Sobol 2.5.0'a girmez (maliyet: Saltelli şeması ile örnek sayısı ~(d+2) kat).
- Tutarlılık garantisi: her MC koşusunun 0 numaralı örneği nominal girdi
  vektörüne sabitlenir ve deterministik hesapla bire bir eşleşmek ZORUNDADIR
  (eşleşmezse iş hata ile düşer). MC ortalaması nominali asla değiştirmez;
  fark "nonlinearity shift" olarak ayrıca raporlanır.

---

## 2. Mevcut durum incelemesi (read-only)

### 2.1 Motor calculate() sözleşmeleri

| Motor | Giriş | Çıkış | Not |
|---|---|---|---|
| `HybridRocketEngine.calculate()` (`hrma/engines/hybrid_rocket_engine.py:180`) | Kurucu parametreleri: thrust/burn_time/total_impulse, of_ratio, chamber_pressure, regression_a/n, fuel_density, fuel_type, oxidizer_type, initial_gox, flux_mode, track_performance... | Düz sözlük: isp, c_star, cf, mdot_*, geometri, grain, kütleler, of_shift_performance, heat_transfer_analysis, structural_analysis, optimum_of_ratio... (`_compile_results`, satır 783) | Denge çözümü Cantera tabanlı CombustionAnalyzer; `_perf_cache` O/F@0.05 çözünürlükte örnek-içi önbellek |
| `SolidRocketEngine.calculate_performance()` (satır 1949) | Kurucu: grain_type, propellant_type, chamber_diameter, grain_length, core_diameter, chamber_pressure, burn_rate_a/n, `overrides=data` (density, char_velocity, ... form alanları) | average_thrust, specific_impulse, burn_time, thrust_curve{time,thrust,pressure}... | `self._ctor_args` saklanıyor — MC yeniden kurulum kalıbı hazır |
| `LiquidRocketEngine.calculate_performance()` (satır 1315) | Kurucu: thrust, chamber_pressure, mixture_ratio, fuel_type, oxidizer_type, cooling_type, injector_type | performans + soğutma + enjektör + turbopompa sözlüğü | DİKKAT: kurucu `_fetch_web_propellant_data` ile CANLI HTTP çağrısı yapıyor (aşağıda) |

### 2.2 app.py akışları

- `/calculate` (satır 288): validator → HybridRocketEngine → injector → validation
  raporu → Plotly grafikleri → (devamında yörünge/CAD). UQ için bu ağır zincirin
  yalnız motor çekirdeği gerekir.
- `/calculate_solid` (1391), `/calculate_liquid` (1460): benzer, daha kısa.
- `/api/solid-monte-carlo` (1522): ZATEN VAR. `SolidRocketEngine.run_monte_carlo`
  (solid_rocket_engine.py:805): n=300 varsayılan, seed=42, 1σ: a ±%3, n ±0.005,
  yoğunluk ±%1, C* ±%1; çıktı mean/std/cv/p5/p95 + ham histogram örnekleri.
  Bu, v2.5.0 genel UQ modülünün embriyosu — istatistik bloğu ve örnekleme deseni
  genelleştirilecek, endpoint geriye uyumlu korunacak.
- `job_runner` (hrma/utils/job_runner.py): thread kuyruğu, 2 worker,
  `progress_callback` enjeksiyonu, TTL 1 saat. `GET /api/jobs/<job_id>` endpoint'i
  MEVCUT (app.py:4496) ve kinetik high-fidelity yolu zaten bu sözleşmeyi kullanıyor
  (202 + poll_url kalıbı, app.py:4477-4481). UQ işleri için DOĞRUDAN KULLANILABİLİR —
  yeni altyapı gerekmez.
- Fidelity kalıbı: `kinetic_efficiency.py` üç seviye tanımlar
  (`fast/engineering/high_fidelity`, `fidelity_used` alanı dürüstlük sözleşmesi).
  UQ seviyeleri aynı adlandırmayı kullanacak.

### 2.3 Kritik runtime bulguları (profil, cProfile)

Hibrit `calculate()` = 1.054 s; dağılımı:

| Blok | Süre | Pay |
|---|---|---|
| `find_optimum_of_ratio` (scipy minimize_scalar, 26 denge çözümü) | 0.715 s | %70 — danışma çıktısı, MC örneğinde gereksiz |
| `_design_fuel_grain` içindeki `_instantaneous_performance` (O/F kayması, 200 adım) | 0.190 s | örnek-içi cache var ama örnekler ARASI paylaşılmıyor |
| `_calculate_c_star` + diğer denge çözümleri | ~0.07 s | |
| injector `_solve_circuit` (NHNE) | 0.064 s | |
| ısı + yapısal + derleme | ~0.03 s | ucuz — MC'de tutulabilir |

Sıvı `calculate_performance()` = 659 ms'nin 658 ms'si `__init__` →
`web_propellant_api.get_comprehensive_data` → `fetch_spacex_telemetry` CANLI
HTTP isteği (requests.get, timeout 30 s!). Gerçek hesap 0.3-0.4 ms. Pickle
cache (TTL 1 saat) var ama benchmark'ta her kurucu çağrısında ağa çıktı —
MC yolunda ağ çağrısı örnek başına KESİNLİKLE yasak; veri bir kez çekilip
enjekte edilecek (bkz. 6.3). Ayrıca `optimum_of` `_compile_results`'ta
`if optimum_of:` ile korunuyor — falsy dönerse temiz atlanıyor; `uq_mode`
bayrağı bunu kullanır.

---

## 3. Runtime ölçümleri ve MC bütçesi

Ortam: Berke'nin Mac'i (darwin, Anaconda py3.12, numpy 1.26.4, scipy 1.13.1).
Komut dosyası: `scratchpad/bench_uq.py`, `scratchpad/prof_uq.py` (20 çağrı ort.,
2 warmup; girdi pertürbasyonlu ölçümlerde OF ±%2, Pc ±%1 örneklendi ki önbellek
iyimserliği olmasın).

| Konfigürasyon | Örnek başı | 200 örnek | 1000 | 5000 |
|---|---|---|---|---|
| HYBRID naif calculate() | 1037 ms | 207 s | 17.3 dk | 86 dk |
| HYBRID uq_mode (opt-OF atla), track=True | 354 ms | 71 s | 5.9 dk | 29.5 dk |
| HYBRID uq_mode, track=False | 133 ms | 27 s | 2.2 dk | 11.1 dk |
| HYBRID uq_mode + denge memoizasyonu (OF@0.01, Pc@0.1), track=False | 91 ms | 18 s | 1.5 dk | 7.6 dk |
| HYBRID uq_mode + memo, track=True | 185 ms | 37 s | 3.1 dk | 15.4 dk |
| SOLID calculate_performance() | 3.2 ms | 0.6 s | 3.2 s | 16 s |
| LIQUID (ağ paylaşımlı, kur+hesap) | 0.4 ms | 0.1 s | 0.4 s | 2 s |
| LIQUID naif (her örnekte HTTP!) | 659 ms | — | — | YASAK |

Memoizasyon notu: denge çözümü anahtarı (yakıt, oksitleyici, OF 2 ondalık,
Pc 1 ondalık); 40+ örnek sonunda tablo ~102 girdide doyuyor (pertürbasyon bandı
sınırlı olduğundan), isabet oranı örnek sayısıyla artar. Yuvarlama YALNIZ denge
tablosunun anahtarında — örneklenen girdi değerleri yuvarlanmaz; c* yüzeyi
(OF, Pc) üzerinde pürüzsüz olduğundan 0.01/0.1 çözünürlüğün c* hatası << %0.1
(mevcut `_perf_cache` zaten O/F@0.05 yuvarlıyor; bu daha sıkı).

### Seviye başına örnek bütçesi önerisi (ölçüme dayalı, x1.5 yaşlı-donanım payı)

| Seviye | Hibrit | Katı | Sıvı | Hibrit tahmini süre | Koşum yolu |
|---|---|---|---|---|---|
| Fast Screening | 200 | 500 | 500 | ~20-30 s (memo, track=False) | job_runner (progress'li) |
| Engineering | 1000 | 2000 | 2000 | ~1.5-3 dk (memo, track=False) | job_runner |
| High-Fidelity | 3000 | 5000 | 5000 | ~9-14 dk (memo, track=True: O/F kayması ort. Isp dahil) | job_runner |

Katı/sıvı her seviyede saniyeler mertebesinde — bütçeyi hibrit belirliyor.
Seviye ayrımı hibritte yalnız örnek sayısı değil fizik kapsamı da değiştirir:
Fast/Engineering `track_performance=False` (Isp tasarım O/F'sinde),
High-Fidelity `track_performance=True` (zaman-ortalamalı Isp dağılımı da çıkar).
Yanıttaki `fidelity_used` + `n_samples` alanları ne koşulduğunu dürüstçe söyler
(kinetic_efficiency sözleşme kalıbı).

---

## 4. Girdi belirsizlik modeli

İlke: her parametre çarpımsal pertürbasyon faktörü olarak örneklenir
(λ = X/X_nominal), fiziksel sınırlarda kırpılmış (truncated) normal varsayılan.
Çarpımsal form birim bağımsızdır ve mevcut katı MC kalıbıyla (1 + N(0,σ)) uyumlu.
Kullanıcı istekte `uncertainty_overrides` ile her dağılımı değiştirebilir/kapatabilir.

### 4.1 Hibrit (öncelik sırasıyla)

| Parametre | Dağılım (varsayılan) | Gerekçe / kaynak |
|---|---|---|
| Regresyon hızı çarpanı λ_r (a'ya uygulanır) | N(1, 0.15), kırp [0.6, 1.4] | Hibrit regresyon korelasyonlarının tesisler arası saçılımı ±%20-30, aynı tesiste ±%10-15: Chiaverini & Kuo (ed.), "Fundamentals of Hybrid Rocket Combustion and Propulsion", AIAA Prog. Astro. Aero. Vol. 218, 2007; Karabeyoglu et al., J. Propulsion and Power 20(6), 2004 (parafin veri saçılımı); Zilliac & Karabeyoglu, AIAA 2006-4504 (aynı yakıt için yayınlar arası bant). HRMA katsayı tablosunun kendisi kaynaklı (Doran AIAA 2007-5352 vb., propellant_database.py:31) — belirsizlik korelasyonun kendi bandıdır |
| Regresyon üssü n (mutlak) | N(n_nom, 0.03), kırp [0.3, 0.85] | Log-log fit güven aralığı; literatür fitlerinde n ±0.02-0.05 tipik (Zilliac & Karabeyoglu 2006, Tablo 2 fitleri) |
| c* verimi η_c* | N(0.93, 0.03), kırp [0.80, 1.00] | Hibritlerde karışım sınırlı yanma verimi 0.85-0.95 tipik; sıvılarda 0.92-0.99 (Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 5 ve 16). `analyze_combustion(eta_c_star=...)` parametresi ZATEN VAR (combustion_analysis.py:146) — UQ katmanı doğrudan geçirir |
| Yakıt yoğunluğu ρ_f | N(1, 0.02) çarpan, kırp [0.94, 1.03] | Döküm boşlukları/büzülme; parafin büzülmesi %2-3'e çıkar (Karabeyoglu 2004); katı MC'deki ±%1'den bilinçli geniş |
| Enjektör Cd | N(0.70, 0.05), kırp [0.5, 0.9] | İki fazlı N2O boşalma katsayısı belirsizliği; Dyer NHNE modeli ±%15 kütle debisi bandı (Dyer et al., AIAA 2007-5703; Waxman et al. ölçümleri). HRMA enjektör modülü Dyer NHNE kullanıyor (injector_design.py) |
| Boğaz boşalma katsayısı CD_t | N(0.98, 0.005), kırp [0.95, 1.0] | Sutton 9. baskı Böl. 3 (0.97-0.99 tipik); kod sabiti 0.98 (hybrid_rocket_engine.py:205) |
| Nozul sapma verimi λ_div | N(λ_nom, 0.005), kırp [0.95, 1.0] | Geometrik (15° koni λ=0.983, bell λ tablolu); belirsizlik küçük — düşük öncelik |
| Kamara basıncı kontrol toleransı | N(1, 0.02) çarpan | Besleme sistemi regülasyonu ±%2-3 (blowdown N2O'da daha yüksek — transient modül ayrı); tasarım noktası belirsizliği olarak |
| G_ox tasarım akısı | N(1, 0.05) çarpan | mdot_ox ölçüm/kontrol belirsizliği; port boyutlandırmayı etkiler |

NOT — a-n korelasyonu: a ve n aynı log-log regresyondan geldiği için güçlü
negatif korelasyonludur; ikisini bağımsız örneklemek varyansı ŞİŞİRİR. Varsayılan
model bu yüzden a'yı λ_r çarpanı ile pertürbe eder (korelasyon problemi yok),
n'yi ayrı ve DAR pertürbe eder. Gelişmiş kullanıcı (a, n) kovaryansı verirse
Cholesky ile ortak örnekleme (v2.5.0 kapsamında API'de yer ayrılır, UI'da yok).

### 4.2 Katı (mevcut run_monte_carlo modeli genişletilir)

| Parametre | Dağılım | Kaynak |
|---|---|---|
| Yanma hızı a | N(1, 0.03) çarpan (mevcut) | Lot-to-lot yanma hızı tekrarlanabilirliği ±%1-3: NASA SP-8064, "Solid Propellant Selection and Characterization", 1971 |
| Üs n | N(n, 0.005) mutlak (mevcut), kırp [0.1, 0.99] | Aynı; üretim toleransı (korelasyon fiti değil) |
| Yoğunluk | N(1, 0.01) çarpan (mevcut) | Döküm kalite kontrol bandı |
| c* | N(1, 0.01) çarpan (mevcut) | Kompozisyon toleransı |
| YENİ: sıcaklık duyarlılığı σ_p ile başlangıç sıcaklığı | U(-10, +35) °C opsiyonel | NASA SP-8064; motor zaten initial_temp override'ı işliyor |
| YENİ: çekirdek çapı toleransı | N(0, 0.2 mm) mutlak | Mandrel/işleme toleransı |

### 4.3 Sıvı

| Parametre | Dağılım | Kaynak |
|---|---|---|
| η_c* | N(0.96, 0.02), kırp [0.88, 1.0] | Sutton 9. baskı: iyi tasarlanmış sıvı enjektörlerde 0.92-0.99 |
| Karışım oranı kontrolü | N(1, 0.02) çarpan | Debi kontrol vanası/venturi toleransı ±%1-3 |
| Pc | N(1, 0.02) çarpan | Regülatör bandı |
| Soğutma tarafı (duvar sıcaklığı çıktısına) | v2.5.0'da girdi pertürbasyonu yok; çıktı dağılımı diğer girdilerden türetilir | Bartz korelasyonunun kendi ±%20-30 bandı v2.6 adayı (model-formu belirsizliği, parametre belirsizliği değil) |

Tüm varsayılanlar `uq_defaults` tablosunda kaynak dizesiyle (İngilizce künye)
birlikte durur ve YANIT içinde `inputs_used[].source_note` olarak yankılanır —
mühendis hangi varsayımın nereden geldiğini API'den görür (güven sürümünün ruhu).

---

## 5. Örnekleme ve duyarlılık

### 5.1 Latin Hypercube (LHS)

- `scipy.stats.qmc.LatinHypercube(d=n_param, seed=seed)` → [0,1)^d tabakalı
  örnekler → her marjinal için inverse-CDF (truncated normal:
  `scipy.stats.truncnorm.ppf`, uniform: doğrusal). scipy 1.13.1 KURULU ve
  requirements'ta `scipy>=1.11.0` — qmc scipy 1.7'den beri stdlib-scipy'de.
  YENİ BAĞIMLILIK YOK; numpy<2 pini ve PyInstaller bundle etkilenmez.
- Fallback (savunmacı): scipy.qmc import edilemezse 12 satırlık saf-numpy LHS
  (her boyutta permütasyonlu tabaka + tabaka içi uniform). Testte iki yol da
  doğrulanır; bundle'da scipy zaten şart (engines scipy.optimize kullanıyor).
- Neden LHS: aynı N'de ortalama/std kestirim varyansı plain MC'den belirgin
  düşük (tabakalı marjinaller); N=200'lük Fast seviyesinin "anlamlı" olmasını
  sağlayan şey budur. Plain MC seçeneği `sampler: "mc"` ile korunur
  (istatistiksel testler ve bootstrap CI için).
- Percentil güveni: P5/P95 için N=200'de bootstrap CI genişletilmiş raporlanır
  (bkz. 7.2 yanıt şeması `ci_mean` / `pXX_ci`); N=1000+ önerisi UI'da not düşülür.

### 5.2 Duyarlılık: Spearman + tornado

- MC örnek matrisi (N x d) ile her ana çıktı vektörü arasında Spearman sıra
  korelasyonu (`scipy.stats.spearmanr` — mevcut). Maliyet: sıfır ek model koşusu.
- Tornado diyagramı: |rho| azalan sırada yatay çubuklar; işaret yön bilgisi.
  Monotonluk varsayımı sınırlaması yanıtta `method_note` ile açıkça belirtilir
  (Spearman monotonik-olmayan etkileşimleri ıskalar).
- Sobol NEDEN 2.5.0'DA YOK: birinci-derece + toplam indeks için Saltelli şeması
  N x (d + 2) koşum ister; d=8, N=1000 → 10 000 koşum ≈ hibritte 15-30 dk
  (ölçülen 91-185 ms/örnek ile). Ön tasarım aracında sıralama (ranking) için
  Spearman yeterli; Sobol ancak vekil model (PCE/GP) üstünde anlamlı maliyete
  iner — v2.6 adayı olarak nota geçildi.

---

## 6. Mimari

### 6.1 Yeni modüller

```
hrma/analysis/uncertainty.py        (YENİ, ~450-550 satır)
  - UncertainInput: name, dist('truncnorm'|'uniform'), mode('multiplier'|'absolute'),
    params, bounds, applies_to, source_note
  - DEFAULT_UQ_MODELS = {'hybrid': [...], 'solid': [...], 'liquid': [...]}
    (Bölüm 4 tablolarının kodu; kaynak künyeleri İngilizce string)
  - sample_inputs(model, n, seed, sampler='lhs') -> (N x d) matris + kayıt
  - run_uncertainty(motor_type, motor_inputs, level, n_samples, seed,
                    overrides, progress_callback) -> yanıt sözlüğü
  - _stats_block(samples, nominal): mean/std/cv/p5/p50/p95 + histogram(edges,counts)
    (solid run_monte_carlo._stats genelleştirmesi)
  - spearman_sensitivity(X, y) -> sıralı [{param, rho}]
  - Sabitler: LEVEL_BUDGETS = {'fast':{'hybrid':200,'solid':500,'liquid':500}, ...}

hrma/analysis/uq_adapters.py        (YENİ, ~250-350 satır)
  - HybridUQAdapter: nominal() bir kez tam calculate(); evaluate(sample) uq_mode
    motoru kurar, PAYLAŞILAN memoizasyonlu CombustionAnalyzer enjekte eder,
    eta_c_star'ı geçirir; çıktı vektörünü (isp, thrust, c_star, Pc uyumu,
    port_final, m_f, T_c, ısı/yapısal SF...) döndürür
  - SolidUQAdapter: mevcut _ctor_args + overrides kalıbını sarar
  - LiquidUQAdapter: web verisini BİR KEZ çeker (veya offline store), tüm
    örnek kurucularına enjekte eder — örnek başına HTTP kesinlikle yok
```

### 6.2 Küçük motor düzenlemeleri (davranış değişmez, bayraklı)

| Dosya | Değişiklik | Boyut |
|---|---|---|
| `hybrid_rocket_engine.py` | `uq_mode=False` kurucu bayrağı: True iken `find_optimum_of_ratio` çağrılmaz (compile `if optimum_of:` zaten falsy'yi atlıyor — ölçüldü, güvenli), irtifa/itki-irtifa tabloları atlanır; `combustion_analyzer=None` parametresi (paylaşılan analyzer enjeksiyonu); `eta_c_star=None` geçişi | ~25 satır |
| `combustion_analysis.py` | `CombustionAnalyzer(memoize=False)`: instance-level `{(fuel,ox,OF@0.01,Pc@0.1): sonuç}` önbelleği (yalnız memoize=True iken; varsayılan davranış aynen korunur) | ~15 satır |
| `liquid_rocket_engine.py` | Kurucuya `web_data=None`: verilirse `_fetch_web_propellant_data` atlanır | ~10 satır |
| `solid_rocket_engine.py` | `run_monte_carlo` istatistik bloğu `uncertainty._stats_block`'a delege (davranış ve endpoint sözleşmesi aynı) | ~15 satır |

### 6.3 Paralellik kararı

MC döngüsü TEK thread'de sıralı koşar (job_runner worker'ı içinde), her ~%2'de
`progress_callback`. Multiprocessing BİLİNÇLİ dışlandı: PyInstaller bundle'da
Windows spawn sorunları (mevcut masaüstü dağıtım kısıtı, job_runner docstring'i
Celery'yi de aynı gerekçeyle dışlıyor) + Cantera nesneleri pickle edilemez.
Hibrit yüksek seviye ~9-14 dk sürer; kabul edilebilir çünkü asenkron, progress'li
ve iptal edilebilir (v2.5.0'da iptal: job TTL + UI "yeni koşu eskisini geçersiz
kılar" notu; hard-cancel v2.6).

---

## 7. API sözleşmesi

### 7.1 İstek — `POST /api/uncertainty-analysis`

```json
{
  "motor_type": "hybrid",              // hybrid | solid | liquid
  "motor_inputs": { ... },             // ilgili /calculate* ile AYNI form alanları
  "level": "engineering",              // fast | engineering | high_fidelity
  "n_samples": null,                   // null -> LEVEL_BUDGETS; verilirse [50, 10000] kırp
  "seed": 42,                          // varsayılan 42 (solid MC ile tutarlı)
  "sampler": "lhs",                    // lhs | mc
  "uncertainty_overrides": {           // opsiyonel; parametre kapatma/değiştirme
    "regression_lambda": {"dist": "truncnorm", "sigma": 0.10},
    "cd_injector": null                // null -> bu parametre deterministik kalır
  }
}
```

Dönüş: `202 {"status":"queued","job_id":"...","poll_url":"/api/jobs/<id>",
"estimated_seconds": ...}` — kinetik high-fidelity kalıbının aynısı
(app.py:4477). Katı/sıvı Fast istekleri de tutarlılık için aynı asenkron yoldan
gider (saniyeler içinde `done` olur; UI tek kod yolu tutar).

### 7.2 İş sonucu (`GET /api/jobs/<id>` → `result`)

```json
{
  "status": "success",
  "motor_type": "hybrid", "level": "engineering",
  "n_samples": 1000, "n_failed_runs": 3, "seed": 42, "sampler": "lhs",
  "fidelity_notes": "track_performance=False at this level; ...",
  "nominal": {"isp": 205.3, "thrust": 1000.0, "c_star": 1524.1, "...": "..."},
  "outputs": {
    "isp": {
      "nominal": 205.3, "mean": 204.9, "std": 4.1, "cv_percent": 2.0,
      "p5": 198.0, "p50": 205.0, "p95": 211.4,
      "mean_ci95": [204.6, 205.2],          // CLT / bootstrap
      "histogram": {"edges": [...31 değer...], "counts": [...30 değer...]}
    },
    "thrust": {"...": "..."}, "c_star": {}, "total_impulse": {},
    "port_diameter_final": {}, "fuel_mass": {}, "chamber_temperature": {},
    "max_pressure": {}                        // katı için; motor tipine göre küme
  },
  "sensitivity": {
    "isp": [{"param": "eta_c_star", "spearman": 0.91},
             {"param": "regression_lambda", "spearman": -0.31}, "..."],
    "method_note": "Spearman rank correlation on MC sample; monotonic effects only."
  },
  "inputs_used": [
    {"name": "regression_lambda", "dist": "truncnorm(1, 0.15, [0.6, 1.4])",
     "source_note": "Chiaverini & Kuo 2007; Karabeyoglu 2004 regression scatter"}
  ],
  "consistency": {
    "nominal_check": "passed",               // örnek #0 kontrolü — aşağıda
    "mean_shift_percent": {"isp": -0.19},
    "note": "MC mean differs from nominal due to input-output nonlinearity (Jensen gap); the nominal deterministic value remains the design point."
  },
  "timing": {"wall_s": 96.2, "per_sample_ms": 93.1}
}
```

Histogramlar SUNUCUDA binlenir (30 kutu): 5000 örnek x 8 çıktı ham dizisi
~300+ KB JSON şişirir (mevcut solid MC ham örnek döndürüyor — yeni sözleşmede
bu düzeltilir; solid endpoint'i geriye uyum için eski şemasında kalır).
`sanitize_json_values` mevcut yardımcıyla NaN/inf temizliği.

### 7.3 Deterministik tutarlılık garantisi (tasarımın omurgası)

1. Örnek #0 her koşuda nominal girdi vektörüne SABİTLENİR (tüm çarpanlar 1,
   mutlaklar nominal). Çıktıları, aynı `uq_mode` yolundan hesaplanan nominal ile
   bire bir (rel. 1e-9) eşleşmek zorundadır — eşleşmezse iş `error` durumuna
   düşer ("UQ path diverged from deterministic path" + hangi çıktı). Bu, uq_mode
   kısayollarının fiziği değiştirmediğinin HER KOŞUDA çalışan kanıtıdır.
2. `uq_mode` nominal çıktısı ile TAM `calculate()` nominal çıktısı arasındaki
   eşitlik ayrıca birim testte kilitlenir (atlanan bloklar — opt-OF, irtifa
   tabloları — ana çıktıları beslemiyor; profil bunu doğruladı, test garantiler).
3. MC ortalaması nominalden farklıysa (nonlinearite) nominal ASLA değiştirilmez;
   fark `mean_shift_percent` olarak raporlanır ve UI kartında nominal değer +
   etrafında CI gösterilir. Kural: "nokta tahmin tasarım değeridir, dağılım onun
   güven bağlamıdır."

---

## 8. UI — UNCERTAINTY paneli

- `hrma/static/js/panels/uncertainty_panel.js` (YENİ): mevcut güverte kalıbı
  (`window.AnalysisDock`, validation_panel.js deseni: kendi butonu, buildPayload
  dışı özel istek gövdesi, plotly_dark sarmalayıcı, İngilizce UI metinleri,
  emoji yok).
- Bileşenler:
  1. Seviye seçici (Fast 200 / Engineering 1000 / High-Fidelity 3000 — motor
     tipine göre bütçe ve tahmini süre etiketi ölçümlerden),
  2. Koş butonu → 202 → `poll_url` yoklama → job_runner `progress` alanından
     ilerleme çubuğu,
  3. CI kartları: Isp / İtki / c* / (katıda tepe basıncı) için "nominal
     [P5 — P95]" + cv%,
  4. Histogram (Plotly bar, seçilebilir çıktı),
  5. Tornado (yatay bar, Spearman, işaretli),
  6. "Assumptions" açılır tablosu: `inputs_used` künyeleriyle — mühendis güveni
     için varsayım şeffaflığı,
  7. `consistency.note` bilgi satırı.
- Motor hesabı (`currentResults`) yokken panel pasif (mevcut panel kalıbındaki
  currentResults koruması); motor girdileri son `/calculate*` formundan alınır.

---

## 9. Tekrarlanabilirlik ve seed yönetimi

- Tek seed girişi: `seed` (varsayılan 42, solid MC ile tutarlı).
  `np.random.default_rng(seed)` + `qmc.LatinHypercube(d, seed=seed)`.
  Aynı (girdi, seed, n, sampler, sürüm) → bit düzeyinde aynı JSON.
- Yanıt her zaman `seed`, `sampler` ve modül şema sürümünü (`uq_version: "1"`)
  yankılar — korelasyon raporları ve testler bunu referans alır.
- Platform notu: PCG64 ve truncnorm.ppf aynı numpy/scipy sürümlerinde
  deterministiktir; bundle sürümleri pinli olduğundan dağıtımlar arası
  tekrarlanabilirlik garanti. Kaynak kurulumda scipy minör farkı qmc örnek
  SIRASINI değiştirebilir — dokümana "reproducibility is guaranteed per
  pinned environment" notu.

---

## 10. Test stratejisi

| Test | İçerik | Süre etkisi |
|---|---|---|
| Seed determinizmi | Aynı seed iki koşu → çıktı sözlükleri bire bir eşit; farklı seed → farklı | katı adaptörle ~2 s |
| Bilinen dağılım | Adaptör yerine oyuncak model y = 2x1 + x2 (analitik mean/std); LHS N=200'de mean hatası < %0.5, std < %3 | < 1 s |
| LHS tabakalama | Her marjinalde her tabakada tam 1 örnek; fallback numpy LHS aynı testten geçer | < 1 s |
| Nominal tutarlılık | Örnek #0 == deterministik uq_mode nominali (1e-9); uq_mode nominal == tam calculate() nominal ana çıktılarda (1e-9) | hibrit 1 tam + 1 uq çağrı ≈ 1.5 s |
| Spearman doğruluğu | y=x1 → rho≈1; bağımsız girdi → |rho| < 0.15 (N=200) | < 1 s |
| Endpoint sözleşmesi | POST → 202 şeması → poll → done → yanıt anahtarları; hatalı motor_type/level → 400 | katı ile ~3 s |
| Hibrit uçtan uca (küçük N) | N=25, memo paylaşımı açık; çıktı şeması + n_failed_runs sayacı | ~3-5 s |
| Geriye uyum | /api/solid-monte-carlo eski şemasını aynen döndürüyor | ~2 s |

Toplam CI eklentisi ~15-25 s (mevcut 1088 test süitine oransal olarak küçük).
Uzun bütçe (N=1000+) testleri `slow` işaretli, CI dışı.

---

## 11. Efor tahmini ve dalga yapısı

Dosya bilançosu: 3 YENİ (uncertainty.py, uq_adapters.py, uncertainty_panel.js),
5 KÜÇÜK DÜZENLEME (hybrid_rocket_engine.py, combustion_analysis.py,
liquid_rocket_engine.py, solid_rocket_engine.py, app.py), 1 YENİ test dosyası,
2 doküman güncellemesi (USER_MANUAL.md, SPACE_CAPABILITY.md). Toplam ~1500-1900
yeni satır.

| Dalga | Kapsam | Ajan | Bağımlılık |
|---|---|---|---|
| U1 — Çekirdek | uncertainty.py + uq_defaults tabloları + hibrit adaptörü + motor bayrakları (uq_mode, memoize, eta_c_star geçişi) + çekirdek testler | developer + tester (2) | — |
| U2 — Kapsam + API | katı/sıvı adaptörleri, solid run_monte_carlo delegasyonu, /api/uncertainty-analysis + job entegrasyonu, endpoint testleri | developer (1) | U1 |
| U3 — UI + doküman | uncertainty_panel.js, kılavuz bölümleri, korelasyon raporu ayağıyla (diğer ARGE ajanı) şema hizalama | developer (1) | U2 |
| Denetim | reviewer pass (kritik dosyalar: engines/*, app.py — Code Değişiklik Protokolü) | reviewer (1) | U1-U3 |

Dosya çakışma notu: U1'in motor düzenlemeleri ile U2'nin app.py işi ayrık küme;
paralel dispatch yalnız U1 içindeki developer/tester ayrımıyla (farklı dosyalar)
güvenli — aynı dosyaya iki ajan kuralı gereği sıralı.

---

## 12. Berke onayı gereken açık kararlar

1. a-n belirsizlik modeli: varsayılan λ_r çarpanı (önerilen) mi, (a, n) bağımsız
   pertürbasyon mu, yoksa kovaryanslı ortak örnekleme mi? Öneri: λ_r + dar n;
   kovaryans API'de rezerve, UI'da yok.
2. Hibrit High-Fidelity bütçesi: 3000 örnek ≈ 9-14 dk kabul mü? Alternatif:
   2000 (≈6-9 dk) veya High'da da track=False (5000 ≈ 8-11 dk, O/F kayması
   dağılımından vazgeç).
3. η_c* belirsizliği F-sabit sözleşmesiyle etkileşir: F girdi olduğundan düşük
   η_c* → yüksek mdot/daha büyük boğaz olarak yansır (motor sözleşmesi böyle).
   "F sabit" yorumu mu, "geometri sabit, F dağılır" yorumu mu? Öneri: v2.5.0'da
   mevcut sözleşmeye sadık kal (F sabit), yanıtta yorum notu; geometri-sabit modu
   v2.6.
4. Sıvı motor kurucusundaki canlı HTTP çağrısı UQ dışında da 0.66 s/istek
   maliyeti ve 30 s timeout riski taşıyor — UQ kapsamında sadece enjeksiyonla
   çözülüyor; kurucudan tamamen çıkarılması (ayrı perf düzeltmesi) v2.5.0'a
   alınsın mı?
5. /api/solid-monte-carlo geleceği: geriye uyumla korunsun (önerilen) mü,
   deprecation notuyla yeni endpoint'e yönlendirilsin mi?

---

## Ek — ölçüm artefaktları

- `scratchpad/bench_uq.py` — üç motorun tek-hesap süreleri (20 çağrı ort.)
- `scratchpad/prof_uq.py` — hibrit cProfile sıcak nokta dökümü
- Ham sonuçlar bu rapordaki tablolara işlendi; /tmp kalıcı değildir, kalıcı
  kopya bu dosyadır.
