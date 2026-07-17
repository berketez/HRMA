# HRMA v2.5.0 — Gerçek-Deney Doğrulama Veritabanı + Otomatik Korelasyon Raporu
## ARGE Tasarım Dokümanı (kod yazılmadı, salt tasarım)

Tarih: 2026-07-17
Kapsam: "Güven Sürümü" ikinci ayak — açık literatürdeki gerçek static-fire /
motor verisinden doğrulama veritabanı ve HRMA tahminleriyle otomatik
korelasyon raporu altyapısı.

---

## 1. MEVCUT DURUM ENVANTERİ (read-only inceleme sonucu)

### 1.1 `hrma/validation/` — dört modül, dört farklı iş

| Modül | Ne yapıyor | v2.5.0'daki rolü |
|---|---|---|
| `motor_validation.py` (`MotorDataValidator`) | Girdi aralık/tutarlılık denetimi (fiziksel limitler, yakıt kombinasyonu, güvenlik uyarıları). Deneysel doğrulama DEĞİL. | Dokunulmaz; adı yanıltıcı ama işi girdi hijyeni. |
| `validation_system.py` (`ValidationSystem`) | Gerçek zamanlı parametre-aralık uyarıları (Sutton tabanlı bantlar, ima edilen CF denetimi). | Dokunulmaz. |
| `experimental_validation.py` (`ExperimentalValidation`) | **11 SENTETİK kayıt** (6 "literatür" + 2 "üniversite" + 3 "benchmark" arketipi; sinüs + tohumlu Gauss gürültüsü ile üretilmiş zaman serileri). SQLite'a (`data/experimental_data.db`, gitignore'lu) yazar. `validate_hrma_predictions` var ama döngüsellik dersi öğrenilmiş: varsayılan parametre listesi yalnız `isp` ve `mass_flow_rate` (thrust/Pc girdi olduğu için tahmin sayılmaz — docstring'de açıkça yazılı). Modül başında dürüst provenans notu var: "must NOT be reported as experimental validation". | **Yeniden yapılandırılacak** (Bölüm 3.1). |
| `user_data_validation.py` (Dalga 4A) | Kullanıcının KENDİ static-fire CSV'sini HRMA itki eğrisiyle karşılaştırır. Sağlam metrik makinesi: I_t (Sutton Eş. 2-1, yamuk kuralı), NFPA 1125 %5 yanma penceresi, F_avg, tepe itki, RMSE/NRMSE, İngilizce değerlendirme metni. 30+ testle korunuyor. | **Yeniden kullanılacak** — eğri karşılaştırma çekirdeği korelasyon koşucusunun p-t/F-t karşılaştırmasında aynen çağrılır. |

### 1.2 Kritik bulgu — ölü endpoint

`app.py` satır 3448 ve 3629: `/api/experimental-validation` endpoint'i
`experimental_validator.validate_against_experiments(...)` ve
`calculate_confidence_metrics(...)` çağırıyor; **bu metotlar
`ExperimentalValidation` sınıfında YOK** (sınıfta olan
`validate_hrma_predictions`). Endpoint çağrılırsa AttributeError → generic
500 döner. `hrma/static/js/` içinde bu endpoint'e hiçbir referans yok —
yani ölü kod, kimse fark etmemiş. v2.5.0'da bu endpoint ya emekli edilmeli
ya da yeni korelasyon koşucusuna bağlanmalı (Bölüm 3.5, karar K5).

### 1.3 Diğer envanter

- **`VALIDATION_STATUS.md`**: elle bakılan, dürüst ve kaliteli bir belge
  (verification/validation ayrımı AIAA G-077 diliyle, bilinen limitler,
  güven zarfı). Sorun: her fizik değişikliğinde elle güncellenmesi gerekiyor
  ve sayısal iddiaları (18/18 çift ≤1.5 % vb.) hiçbir script yeniden üretmiyor.
- **Kullanıcı-CSV modu** (`/api/validation/upload-csv`, app.py ~4514):
  JSON `{csv_text, predicted_curve}` alır, parse + compare döner; hata
  gövdesinde `parsed` taşıma deseni panelle sözleşmeli.
- **`validation_panel.js`**: AnalysisDock `register()` kalıbı + özel form
  bloğu enjeksiyonu + Plotly çizim + `window.ValidationPanel` test kancaları.
  Gerçek-veri sekmesi bu kalıbı birebir kopyalayabilir.
- **Testler**: `test_user_validation.py` (30+ test, el-çapa değerli),
  `test_hybrid_regression_validation.py` zaten TEK gerçek deney çapasını
  içeriyor (Rezaei et al. HTPB/N2O: G_ox=68.8 kg/m²s, r_meas=0.779 mm/s,
  c*_meas=1513 m/s) — yani "gerçek veri + pytest bekçisi" deseni embriyonik
  olarak mevcut, genelleştirilecek.
- **`data/nasa_realtime_validator.py`**: RS-25/F-1 gibi resmi motor
  spec'lerini gömülü tutuyor — bu sabit noktalar yeni DB'ye "motor düzeyi
  kamu spec'i" kaydı olarak taşınabilir.
- **Altyapı hazır parçalar**: `job_runner` (uzun koşular için), `reportlab`
  (PDF, bundle'da), Plotly koyu tema sarmalayıcı, AnalysisDock.
- `hrma/__init__.py`: `DATA_DIR = <repo>/data` — gitignore'lu, çalışma
  zamanı ürünleri için. Gerçek deney kayıtları buraya KONMAMALI (sürüm
  kontrolü şart).

---

## 2. DENEY VERİTABANI TASARIMI

### 2.1 Depolama biçimi: git-izlenen JSON dosyaları (SQLite değil)

Karar önerisi: kayıt başına bir JSON dosyası,
`hrma/validation/experiments/<motor_type>/<test_id>.json`.

Gerekçe (SQLite'a karşı):
- Gerçek deney verisi **küratörlük ürünüdür**: her kayıt diff'lenebilir,
  PR'da gözle incelenebilir, kaynağa kadar izlenebilir olmalı. SQLite blob'u
  bunların hiçbirini vermez; mevcut `experimental_data.db` zaten gitignore'lu
  ve her açılışta yeniden üretiliyor.
- Kayıt sayısı onlarca mertebesinde (yüz binler değil) — ilişkisel sorgu
  ihtiyacı yok; loader başlangıçta hepsini belleğe alır.
- JSON Schema ile makine doğrulaması (`schema.json` + pytest) mümkün.
- SQLite katmanı tamamen kaldırılır; `experimental_data.db` üretimi durur.

### 2.2 Kayıt şeması (JSON Schema draft-07 ile denetlenecek)

```json
{
  "schema_version": "1.0",
  "test_id": "hyb-rezaei2018-htpb-n2o-01",
  "record_type": "static_fire | flight | engine_spec",
  "motor_type": "hybrid | solid | liquid",

  "source": {
    "citation": "Rezaei, H. et al., 'Experimental investigation of HTPB/N2O...', Scientia Iranica, 25(5), 2018",
    "doi": "10.24200/sci.2017.4506",
    "url": "https://...",
    "access_status": "open | paywalled | public_domain | webpage",
    "data_extraction": "table | text | figure_digitized | vendor_datasheet",
    "extraction_note": "Şekil 5'ten WebPlotDigitizer ile sayısallaştırıldı; sayısallaştırma belirsizliği ~±2 %",
    "entered_by": "claude/berke",
    "entered_date": "2026-07-18",
    "reviewed": false
  },

  "propellants": {
    "oxidizer": "n2o",
    "fuel": "htpb",
    "grade_note": "R-45M HTPB, %85 katılık ...",
    "hrma_fuel_key": "htpb",
    "hrma_oxidizer_key": "n2o"
  },

  "geometry": {
    "port_diameter_initial_m": 0.05,
    "grain_length_m": 0.30,
    "throat_diameter_m": 0.012,
    "expansion_ratio": 4.5,
    "chamber_diameter_m": 0.08,
    "grain_geometry": "cylindrical | BATES | star | ...",
    "n_segments": 1
  },

  "inputs": {
    "chamber_pressure_bar": 28.6,
    "of_ratio": 1.766,
    "mdot_ox_kgps": 0.135,
    "burn_time_s": 7.0,
    "ambient_pressure_bar": 1.0,
    "_comment": "Bu blok HRMA'ya GİRDİ olarak verilir; buradaki hiçbir alan skorlanamaz (döngüsellik yasağı, Bölüm 3.2)"
  },

  "measured": {
    "c_star_mps": 1513.0,
    "isp_s": null,
    "thrust_mean_n": null,
    "thrust_peak_n": null,
    "total_impulse_ns": null,
    "regression_rate_mmps": 0.779,
    "eta_c_star": 0.97,
    "curves": {
      "pressure_bar": {"time_s": [...], "value": [...]},
      "thrust_n": null
    }
  },

  "measurement_uncertainty": {
    "c_star_mps": {"type": "relative", "value": 0.03, "coverage": "k=2", "source": "makale Bölüm 3.2"},
    "regression_rate_mmps": {"type": "relative", "value": 0.05, "coverage": "stated", "source": "..."},
    "_default_policy": "kaynakta belirsizlik yoksa alan null bırakılır ve korelasyon raporunda 'belirsizlik bildirilmemiş' sınıfına düşer; ASLA uydurulmaz"
  },

  "confidence": "high | medium | low",
  "confidence_rationale": "hakemli dergi + tablo verisi + belirsizlik bildirimi = high",
  "tags": ["university_scale", "lab_scale", "flight_heritage"],
  "synthetic": false,
  "exclude_from_stats": false,
  "exclude_reason": null,
  "notes": "Serbest metin: test standı, enjektör tipi, bilinen anormallikler"
}
```

Şema ilkeleri:
1. **`inputs` / `measured` ayrımı yapısal döngüsellik korumasıdır** —
   `experimental_validation.py`'nin docstring'inde el yordamıyla öğrenilen
   ders ("thrust ve Pc girdi olduğu için tahmin değildir") şemaya
   gömülür: koşucu `inputs` altında görünen bir büyüklüğü skorlamayı
   REDDEDER (Bölüm 3.2).
2. **Belirsizlik asla uydurulmaz.** Kaynakta yoksa null; rapor bu kayıtları
   ayrı sınıfta gösterir. `coverage` alanı (k=1/k=2/stated) NASA-STD-7009 /
   ASME V&V 20 dilinde raporlama için gerekli.
3. **`confidence` üç kademe**:
   - `high`: hakemli yayın + tablo/metin verisi (+ belirsizlik bildirimi)
   - `medium`: hakemli yayın ama şekilden sayısallaştırma; veya kurumsal
     teknik rapor (NASA TM/CR); veya NAR/TRA sertifikasyon eğrisi
     (thrustcurve.org — ölçüm standardı belli, izlenebilirlik orta)
   - `low`: amatör ama iyi belgelenmiş kaynak (Nakka static testleri),
     üretici broşür değeri, ikincil aktarım
   Ana korelasyon istatistiği varsayılan olarak high+medium üstünden
   hesaplanır; low kayıtlar raporda ayrı satırda gösterilir (karar K2).
4. **Telif**: yalnız SAYISAL veri + tam künye saklanır (veri gerçekleri
   telif konusu değildir); makale metni/figür görüntüsü repoya girmez.
   `access_status` alanı paywall'lı kaynaktan alınan veriyi işaretler.

### 2.3 Mevcut 11 sentetik kaydın kaderi — seçenek analizi

| Seçenek | Artı | Eksi |
|---|---|---|
| **(a) Tamamen sil** | Kirlenme riski sıfır; "sentetik veri var mı?" sorusu kökten biter | Korelasyon boru hattının CI'da motor-fiziğinden bağımsız, deterministik test edilmesi için fikstür gerekir — silinirse yeniden yazılır; ölü `/api/experimental-validation` bağımlılığı zaten kırık ama `experimental_validator` import'u app açılışında DB kuruyor, söküm işi aynı |
| **(b) Üretim DB'sinde `synthetic: true` bayrağıyla tut** | Az iş | En tehlikeli seçenek: bayrak filtresi bir yerde unutulursa sentetik kayıt gerçek istatistiğe karışır; "gerçek-veri DB'si" iddiasının altını oyar; paper hakemine anlatması zor |
| **(c) ÖNERİLEN: `tests/fixtures/synthetic_experiments.json`'a taşı, üretim tarafından sök** | Boru hattı CI testi deterministik fikstürle koşar (Cantera/CEA'sız, hızlı); üretim DB'sinde tek bir sentetik satır kalmaz; `experimental_validation.py` + SQLite katmanı + ölü endpoint birlikte emekli edilir; dürüstlük iddiası temiz | Orta boy söküm işi (~0.5 gün); `validation_results.json/png` repo kökündeki eski çıktılar da temizlenmeli |

Öneri: **(c)**. Sentetik kayıtlar şema-uyumlu JSON'a çevrilir
(`synthetic: true`, `confidence: "low"`, `exclude_from_stats: true`),
yalnız `tests/` altında yaşar; loader'ın `include_synthetic` parametresi
varsayılan False ve UI/rapor yolundan bu parametreye erişim YOKtur.
Karar Berke'de (K1).

### 2.4 Aday gerçek veri kaynakları (tohum seti — veri toplama ajanlarının işini bağlamaz, şemanın taşıyabilmesi gerekenleri gösterir)

| Kaynak | Motor tipi | confidence | Not |
|---|---|---|---|
| Rezaei et al. 2018 (HTPB/N2O) | hibrit | high | Zaten test çapası; DB'ye ilk kayıt olarak taşınır |
| Chiaverini et al., JPP 15(3) 1999 (HTPB/GOX) | hibrit | high | Regresyon bandı |
| Karabeyoglu et al. JPP 20(6) 2004 / Zilliac AIAA 2006-4504 (parafin) | hibrit | high | r-G korelasyon verisi |
| Whitmore (Utah State) ABS/N2O serisi | hibrit | high | Basılı ABS greyn, açık makaleler |
| Stanford/NASA Peregrine raporları | hibrit | medium | Ölçek büyütme noktası |
| thrustcurve.org NAR/TRA sertifikasyon eğrileri (Cesaroni/AeroTech) | katı | medium | Ölçülmüş F(t); "küçük katı %40 iyimser" limitinin nicelenmesi için ideal |
| Nakka KNSU/KNDX static testleri | katı | low | Şeker seti zaten Nakka'ya çapalı; karar K2 |
| RS-25 / F-1 / Merlin kamu spec'leri (NASA fact sheet, Sutton tabloları) | sıvı | medium | `record_type: engine_spec`; `nasa_realtime_validator.py` gömülü değerleri buraya taşınır |
| Copenhagen Suborbitals / Purdue açık test raporları | sıvı | medium | Amatör-üstü sıvı static-fire, yayımlı p-t eğrileri |

Hedef v2.5.0 için: **8-15 kayıt** (hibrit ağırlıklı 4-6, katı 3-5, sıvı 3-4).
Şema onlarca kaydı sorunsuz taşır; sayı büyüdükçe kampanya bazlı alt klasör
açılır.

---

## 3. OTOMATİK KORELASYON KOŞUSU

### 3.1 Modül yerleşimi

```
hrma/validation/
  experiments/                 # git-izlenen gerçek kayıtlar
    schema.json                # JSON Schema (tek doğruluk kaynağı)
    hybrid/*.json
    solid/*.json
    liquid/*.json
  experiment_db.py             # loader + şema doğrulama + filtreler (YENİ)
  correlation.py               # koşucu + istatistik + aykırı işaretleme (YENİ)
  correlation_report.py        # markdown/PDF/VALIDATION_STATUS üretimi (YENİ)
  user_data_validation.py      # değişmez; compare() çekirdeği yeniden kullanılır
  (experimental_validation.py  # EMEKLİ — karar K1/K5 sonrası silinir)
data/correlation_cache.json    # son koşu sonucu (gitignore'lu, UI bunu okur)
correlation_baselines.json     # eşik/taban metrikleri — GİT-İZLENİR (repo kökü
                               # veya hrma/validation/ altı; bekçi bunu okur)
```

### 3.2 Girdi eşleme katmanı (adapter)

`correlation.py` içinde motor tipi başına açık eşleme tablosu:

- `hybrid` → `HybridRocketEngine(fuel_type=rec.propellants.hrma_fuel_key,
  oxidizer_type=..., chamber_pressure=rec.inputs.chamber_pressure_bar,
  of_ratio=..., thrust/burn_time=...)` — imza mevcut kodda teyitli
  (thrust/burn_time/total_impulse üçlüsü, flux_mode varsayılan 'total').
- `solid` / `liquid` benzer şekilde kendi motor sınıflarına.
- Eşlenemeyen alanlar (kayıtta olmayan gerekli girdi) motorun varsayılanına
  düşer ve koşucu bunu **`assumed_defaults` listesi** olarak kayıt-sonucuna
  yazar; rapor her testte hangi girdilerin varsayıldığını gösterir
  (dürüstlük: "bu karşılaştırma şu varsayımlarla yapıldı").
- **Döngüsellik bekçisi**: skorlanacak büyüklük listesi kayıt bazında
  `measured` anahtarlarından türetilir ve `inputs`'ta da görünen anahtar
  varsa koşucu o büyüklüğü skor dışı bırakıp kayıt-sonucuna
  `skipped_circular: [...]` yazar. (Örn. Pc girdi verildiyse ölçülen Pc ile
  "doğrulama" yapılamaz.)

### 3.3 Metrikler

Kayıt başına, skorlanabilir her büyüklük için:
`error_pct = (pred − meas) / meas × 100` (işaretli — bias görünür kalsın).

Toplulaştırma, **(motor_type × büyüklük)** hücresi başına:
- N (kayıt sayısı)
- bias = ortalama işaretli hata (%)
- RMS hata (%)
- MAPE ve medyan APE (%) — medyan, aykırıya dayanıklı ana gösterge
- min/maks hata, hangi test_id'de
- confidence kırılımı (high/medium ayrı satır)

Eğri verisi olan kayıtlarda (p-t / F-t): `user_data_validation.compare()`
aynen çağrılır (I_t farkı, tepe, NFPA 1125 yanma süresi, NRMSE) — tek metrik
makinesi, iki tüketici (kullanıcı CSV modu + korelasyon koşusu). Transient
tahmin eğrisi `transient_ballistics` üzerinden üretilir.

**Aykırı işaretleme**: hücre içi |error − medyan| > 3×MAD veya mutlak hata
büyüklük-sınıfı eşiğini (Bölüm 5) 2 kat aşan kayıt `outlier: true` işaretlenir.
Aykırılar İSTATİSTİKTEN ATILMAZ; rapor iki satır verir ("tümü" / "aykırısız")
ve her aykırı test_id + olası neden notuyla listelenir. Sessiz veri atma yok.

### 3.4 Determinizm ve maliyet

- Koşucu saf fonksiyon: aynı DB + aynı kod → aynı sonuç. MC/rastgelelik yok
  (UQ katmanı ayrı, Bölüm 6).
- Tam koşu maliyeti Cantera/CEA çağrıları yüzünden dakikalar mertebesinde
  olabilir → sonuç `data/correlation_cache.json`'a yazılır
  (`{git_sha, hrma_version, timestamp, results}`), UI ve VALIDATION_STATUS
  üretici cache'i okur; yeniden koşu isteğe bağlı.

### 3.5 Endpoint'ler

- `GET /api/validation/correlation-summary` → cache'ten özet (yoksa 404 +
  "run correlation first" mesajı).
- `POST /api/validation/correlation-run` → `job_runner.submit(...)` ile
  arka planda tam koşu; mevcut job status endpoint'i kullanılır (kalıp hazır).
- Ölü `/api/experimental-validation` endpoint'i **kaldırılır** (UI referansı
  yok, çağrılsa 500 veriyor) — karar K5.

---

## 4. RAPOR ÜRETİMİ

### 4.1 VALIDATION_STATUS.md otomatik üretimi (hibrit yaklaşım)

Belgenin değeri elle yazılmış dürüst yorumlarda; tamamı otomatik üretilirse
bu kaybolur. Öneri: **işaretçili bölge** yaklaşımı.

```markdown
<!-- AUTO:CORRELATION BEGIN — elle düzenlemeyin, üretici: python -m hrma.validation.report -->
| Motor | Büyüklük | N | Bias | Medyan APE | RMS | Kaynak güveni |
...
<!-- AUTO:CORRELATION END -->
```

- Üretici script yalnız işaretçiler ARASINI değiştirir; belgenin geri kalanı
  (bilinen limitler, tarihçe, el yorumları) elle kalır.
- "Last updated" satırı ve HRMA sürümü + git SHA otomatik damgalanır.
- pytest bekçisi (Bölüm 5) işaretçi-içi tabloların cache ile tutarlı
  olduğunu da denetleyebilir ("belge bayat" testi — cache'teki sayı ile
  belgedeki sayı uyuşmazsa kırmızı).

### 4.2 UI: validation paneline gerçek-veri sekmesi

Mevcut panel kalıbı korunur; iki yol var:
- (a) `validation_panel.js` içinde alt sekme,
- (b) ÖNERİLEN: ayrı `correlation_panel.js`, aynı `VALIDATION` kategorisinde
  `register()` — mevcut panel "kendi verin", yeni panel "literatür
  korelasyonu"; dosya sahipliği ayrışır (paralel ajan kuralı) ve
  kullanıcı-CSV paneli sözleşmesi (test_wave4a_contract) hiç ellenmiş olmaz.

Panel içeriği:
1. Özet kartlar: motor tipi başına N, bias, medyan APE (statCard kalıbı).
2. Parite grafiği (Plotly): ölçülen-x / tahmin-y, ±%X bantları, nokta rengi
   confidence, hover'da test_id + künye.
3. Test listesi tablosu: test_id, kaynak (DOI linki), büyüklükler, hata %,
   aykırı rozeti.
4. "Run correlation" butonu → job_runner akışı; koşu yoksa cache tarihi
   gösterilir. UI metinleri İngilizce (mevcut UI kuralı), emoji yok.

### 4.3 Paper-kalite korelasyon raporu

`python -m hrma.validation.report --format md|pdf`:
- Markdown: yöntem paragrafı (hangi büyüklükler skorlanır, döngüsellik
  kuralı, veri künyeleri tablosu, belirsizlik politikası), hücre-başına
  istatistik tabloları, kayıt-başına ayrıntı ek tablosu, aykırı listesi.
- Parite + hata-histogram figürleri matplotlib ile PNG (paper'a doğrudan);
  Plotly değil — matplotlib zaten `generate_validation_plots` deseninde var
  ve LaTeX'e temiz girer.
- PDF: `reportlab` (bundle'da mevcut, `export/pdf_generator.py` kalıbı).
- Kaynakça: kayıtlardaki `citation` alanlarından otomatik derlenir; paper'ın
  ilgili bölümü bu rapordan tablo/figür alıp künyeleri bibliyografyaya taşır.

---

## 5. REGRESYON BEKÇİSİ (pytest)

### 5.1 Mimari

`tests/test_correlation_guard.py`:
- Şema testi: `experiments/**/*.json` tamamı `schema.json`'a uyar; test_id
  benzersiz; `synthetic: true` kayıt üretim ağacında YOK (fikstürler hariç).
- Hızlı bekçi (her CI koşusunda): fikstür (sentetik) verisiyle boru hattının
  kendisi — loader, adapter, istatistik, aykırı işaretleme — deterministik
  doğrulanır. Motor fiziği çağrılmaz, saniyeler sürer.
- Fizik bekçisi (`@pytest.mark.slow` veya ayrı işaretle): gerçek DB'nin
  temsili bir alt kümesi (motor tipi başına 2-3 kayıt) gerçekten simüle
  edilir ve metrikler `correlation_baselines.json` eşiklerine vurulur.
  Tam DB koşusu nightly/elle.

### 5.2 Eşik seçim stratejisi: "taban-dondurma + fizik tavanı"

İki katmanlı eşik; ikisi birden aşılırsa test kırılır:

1. **Fizik tavanı** (mutlak, literatür saçılımından; VALIDATION_STATUS
   sınıflarıyla uyumlu):
   - c* (hibrit/sıvı/katı-APCP): medyan APE < %5 (CEA çapraz doğrulaması
     ~%1.5 olduğundan gerçek-veri farkının ana kaynağı η_c* ≈ 0.90-0.97;
     teslim c* skorlanıyorsa %5 makul, teorik c* skorlanıyorsa kayıtta
     η düzeltmesi açık yazılır)
   - teslim Isp: medyan APE < %10 (küçük katılar hariç — onlar bilinen
     limit, ayrı hücre ve gevşek eşik %45 "belgelenmiş iyimserlik" olarak)
   - hibrit regresyon hızı: medyan APE < %35 (batch saçılımı ±%20-30 +
     G_total bilinçli kararı; mevcut Rezaei ~%32 içeride kalmalı)
   - toplam impuls (eğri): |fark| < %10; NRMSE < %20
2. **Taban-dondurma** (göreli): ilk tam koşu metrikleri baseline JSON'a
   yazılır (git-izlenir, PR'da görünür). Bekçi kuralı:
   `metric ≤ max(fizik_tavanı, baseline × 1.25)` — yani fizik değişikliği
   korelasyonu belirgin bozarsa (medyan APE %25'ten fazla kötüleşirse) test
   kırılır, tavanın altında kalan küçük dalgalanmalar kırmaz.
3. **İyileşme de sessiz geçmez**: metrik baseline'ın yarısından iyiye
   giderse test UYARI üretir (xfail değil, `warnings.warn`) — "ya gerçek
   iyileşme ya döngüsellik kaçağı" elle incelensin. (2026-07-12 dersinin
   kurumsallaşması: +%2.5 katı Isp 'uyumu' bug artefaktı çıkmıştı.)
4. Eşik değişikliği = `correlation_baselines.json` diff'i = code review
   konusu. Eşikler kod içine gömülmez (parametre tutarlılığı kuralı).

DB'ye kayıt eklemek metrikleri oynatır → bekçi mesajı "DB değişti mi, fizik
mi değişti?" ayrımını yapabilsin diye baseline dosyasına DB içerik hash'i
de yazılır; hash değiştiyse mesaj "yeni kayıtla baseline'ı yeniden dondur"
der, fizik değişikliğinde "korelasyon geriledi" der.

---

## 6. UQ ENTEGRASYONU (diğer ajanın MC tasarımıyla kesişim)

Yaklaşım: **ASME V&V 20 / NASA-STD-7009 ruhu** — doğrulama tek sayı değil,
belirsizlikleriyle karşılaştırma.

- Kayıt tarafı hazır: `measurement_uncertainty` (k kapsamıyla) şemada var.
- MC motoru geldiğinde koşucu her test için tahmini `p50 [p5, p95]` bandıyla
  üretir (MC ajanının çıktı sözleşmesine bağımlılık: yüzdelik dilimli tahmin
  dağılımı — arayüz gereksinimi olarak MC tasarımına iletilmeli).
- Rapora iki yeni sütun:
  1. **Kapsama**: ölçüm bandı (meas ± U_meas) ile tahmin CI'ı kesişiyor mu
     (evet/hayır + görsel: parite grafiğinde iki yönlü hata çubukları).
  2. **Normalize hata**: `E_n = |pred − meas| / sqrt(u_model² + u_meas²)`
     (ISO 13528 / ASME V&V 20 validasyon belirsizliği yaklaşımı);
     E_n < 2 → "belirsizlikler dahilinde tutarlı". u_meas bildirilmemiş
     kayıtlar bu sütunda "n/a" — uydurma belirsizlik yok.
- Fazlama: korelasyon altyapısı NOKTA tahminle tek başına çalışır ve
  yayınlanır (Dalga V1-V4); UQ sütunları MC motoru merge olduktan sonra
  eklenir (Dalga V5). Bekçi eşikleri nokta metriklerde kalır; E_n bekçisi
  (örn. "kayıtların ≥%80'inde E_n<2") V5'te değerlendirilir.

---

## 7. EFOR TAHMİNİ VE DALGA ÖNERİSİ

| Dalga | İçerik | Dosyalar | Efor |
|---|---|---|---|
| V1 | Şema + `experiment_db.py` loader + şema pytest'i + sentetiklerin fikstüre taşınması + eski modül/SQLite/ölü endpoint sökümü | `experiments/schema.json`, `experiment_db.py`, `tests/test_experiment_db.py`, `tests/fixtures/`, app.py (söküm) | 1 gün |
| V2 | Gerçek veri küratörlüğü: 8-15 kayıt (veri-toplama ajanlarının bulgularından; Rezaei + Nakka + thrustcurve + sıvı spec'leri tohum) | `experiments/**/*.json` | 1-1.5 gün (veri ajanlarıyla paralel) |
| V3 | Korelasyon koşucusu + istatistik + aykırı + baseline dondurma + bekçi | `correlation.py`, `correlation_baselines.json`, `tests/test_correlation_guard.py` | 1 gün |
| V4 | Rapor üretimi: VALIDATION_STATUS işaretçili üretim + md/PDF rapor + figürler; UI sekmesi + 2 endpoint | `correlation_report.py`, `correlation_panel.js`, app.py (2 endpoint) | 1-1.5 gün |
| V5 | UQ birleşimi (MC motoru merge sonrası): CI sütunları, E_n, kapsama grafiği | `correlation.py`, `correlation_report.py` dokunuşları | 0.5 gün |

Toplam: ~4.5-5.5 ajan-günü. V1→V3 sıralı (aynı dosyalara dokunur), V2
küratörlük V1 şeması donduktan sonra paralel koşabilir; V4 UI/rapor V3
sözleşmesine bağlı. Dosya sahipliği kesişimleri: app.py'ye V1 (söküm) ve V4
(ekleme) dokunur → sıralı dispatch.

---

## 8. BERKE ONAYI GEREKTİREN KARARLAR

- **K1 — Sentetik 11 kaydın kaderi**: öneri (c) — üretimden tamamen sök,
  şema-uyumlu fikstür olarak `tests/fixtures/`a taşı (`synthetic: true`,
  istatistik/UI/rapora girmesi yapısal olarak imkansız). Alternatifler ve
  artı/eksi Bölüm 2.3'te.
- **K2 — Düşük güvenli kaynaklar dahil mi**: Nakka static testleri ve
  thrustcurve.org sertifikasyon eğrileri DB'ye girsin mi? Öneri: evet,
  Nakka `confidence: low`, thrustcurve `medium`; ana istatistik
  high+medium, low ayrı satırda. (Şeker seti zaten Nakka'ya çapalı —
  dışlamak tutarsız olur.)
- **K3 — Bekçi eşikleri**: Bölüm 5.2'deki fizik tavanları (c* %5, teslim
  Isp %10, regresyon %35, impuls %10/NRMSE %20, küçük-katı özel hücre %45)
  ve baseline×1.25 kötüleşme kuralı + "aşırı iyileşme uyarısı" onayı.
- **K4 — VALIDATION_STATUS.md işaretçili otomatik bölge**: belgenin el
  yazısı kısımları korunur, yalnız tablolar üretilir; "belge bayat" pytest
  denetimi eklenir. Onay?
- **K5 — Ölü `/api/experimental-validation` endpoint'i**: kaldırılsın mı
  (öneri: evet; UI referansı yok, çağrılınca 500 veriyor), yoksa yeni
  korelasyon endpoint'ine takma ad olarak mı bağlansın?
- **K6 — Depolama biçimi**: git-izlenen JSON kayıtları + SQLite katmanının
  tamamen emekliliği (öneri budur; `data/experimental_data.db` üretimi durur).
- **K7 — Sayısallaştırılmış eğriler v1'de mi**: şekilden WebPlotDigitizer
  ile çıkarılan p-t/F-t eğrileri (ek ~±2 % sayısallaştırma belirsizliğiyle)
  ilk sürümde dahil mi, yoksa v1 yalnız tablo/nokta verisi mi? Öneri:
  dahil — eğri karşılaştırma makinesi hazır, katı motor doğrulaması
  (thrustcurve) eğrisiz zayıf kalır.
