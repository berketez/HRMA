# HRMA Analiz Platformu Planı (Task #7 + #8)

**Tarih:** 2026-07-14 · **Kaynak:** 5 ajanlı ARGE turu (733k token, tüm bulgular test_client ile ampirik doğrulandı)
**Vizyon (Berke):** Motor tasarımcısı ısı, dayanıklılık, basınç/kopma, akışkan — tüm analizleri HRMA'dan yapsın; ANSYS yalnız çok detay durumlara kalsın. Tasarım + hesap + analiz + CAD tek platformda.

## ARGE'nin ana tespitleri

**İyi haber — çekirdek fizik sağlam:**
- `heat_transfer_analysis.py` (829 satır): SI-tutarlı Bartz (Sutton 9. baskı Eq. 8-22), recovery sıcaklığı, bisection enerji dengesi; RS-25 literatür bandına karşı 12 test geçiyor.
- `structural_analysis.py` (820 satır): Lamé kalın cidar, 3 eksenli von Mises, MMPDS sıcaklık deratingi, NASA SP-8007 burkulma, uç kapak/cıvata/yorulma; 23 test geçiyor.
- Panel kalıbı olgun: `injector_panel.js` deseni (resultsProvider + bağımsız form + badge/tablo/Plotly) yeni paneller için referans standart.

**Kötü haber — hesaplanan hiçbir şey kullanıcıya ulaşmıyor:**
- `plots.heat_transfer` ve `plots.structural_analysis` her /calculate'te üretiliyor (251 KB israf) ama HİÇBİR şablon render etmiyor.
- `app.js` rapor exportu backend'in gerçek yapısal sonucunu değil SABİT SF (4.0/3.0/4.0) yazıyor — gerçek analiz UNSAFE derken kullanıcı "güvenli" rapor alabilir. **(dürüstlük sorunu, ilk düzeltilecek)**
- `safety_analysis.py` kendi sabit 250 MPa çeliğiyle hoop hesaplıyor; `structural_analysis` aynı motor için 4130'da 460 MPa + derating kullanıyor → iki panel farklı SF gösterir.
- Isı modülünün cidar sıcaklıkları yapısal modüle akmıyor → hayali 511 K gradyan her sıcak motoru SF≈0.21 UNSAFE'e çökertiyor (gerçek iletim ΔT'si doğal soğutmada ~7 K).
- Malzeme DB'leri ayrık ve uyumsuz (ısı: copper var/titanium yok; yapısal: tersi) — tek malzeme seçip iki analize göndermek şu an imkânsız.

**CFD/kinetik gerçeği (ölçüldü):**
- `cfd_analysis.py` gerçek CFD değil: kütle korunumu yok, 3 iterasyonda ıraksıyor (|u|→7.5e10 m/s), NaN → int dizisi → 500. Yerinde onarım = sıfırdan çözücü yazmak.
- `kinetic_analysis.py`: stiff ODE + explicit RK45 → 10 sn'de fiziksel sürenin %0.0007'si; tek istasyon ~23 dk. Bitse bile isp_loss ≡ 0 döndürüyor (yapısal boş). Ayrıca eksik-tür bugı hızları e13 mertebesine şişiriyor.
- Öneri: ikisini de "gerçekçi hızlı model"le değiştir — quasi-1D sıkıştırılabilir lüle akışı + eksenel Bartz (`nozzle_flow_1d.py`) ve frozen/shifting Isp farkı + JANNAF tarzı η_kin korelasyonu. Bu, "ANSYS'siz ön tasarım" vizyonunun mühendislik karşılığı.

## Dalga planı

### Dalga 0 — Dürüstlük ve güven onarımları (küçük, önce bu)
1. `app.js` rapor exportundaki sabit SF'leri backend `motor.structural_analysis` gerçek sonucuna bağla.
2. `hrma/data/materials_db.py` — merkezi malzeme DB (mekanik+termal tek kayıt; 304/316 ve CuCrZr eklenir); structural/heat/safety oradan okur (parametre tutarlılığı kuralı).
3. Isı→yapısal cidar sıcaklığı aktarımı (`wall_temperature_hot/cold` anahtarları zaten okunuyor) + **iki SF raporu**: SF_basınç (birincil) ve SF_toplam (birincil+ikincil termal) ayrı gösterilir.
4. `gamma`/`molecular_weight` /calculate top-level'ına (Bartz fallback'i kalkar).
5. Kilitleme riski: `/api/kinetic-analysis`, `/api/cfd-analysis`, `/api/professional-analysis` → 501 "yeniden yazılıyor" bekçisi (kinetik çağrısı tek-worker masaüstünde uygulamayı saatlerce kilitleyebiliyor).
6. `/api/advanced-analysis` AttributeError düzeltmesi (analyze_chamber_thermal → analyze_heat_transfer); app.py 366-412'deki render edilmeyen çifte hesap/plot üretimi silinir.
7. Radyasyon terimi notu: kara-cisim varsayımı ~2-5× abartıyor — Leckner düzeltmesi Dalga 3'te.

### Dalga 1 — Analiz Güvertesi (backend değişikliği ~sıfır)
- `analysis_dock.js`: kayıt tabanlı panel çatısı (AnalysisDock.register — kategori sekmeleri: ISI / YAPISAL / BASINÇLI KAP / GÜVENLİK / PERFORMANS / AKIŞ / UÇUŞ), injector_panel kalıbı.
- İlk üç panel: `structural_panel.js`, `thermal_panel.js`, `safety_panel.js` — endpoint'ler zaten <1 sn'de 200 dönüyor (/analyze_structural_safety, /analyze_thermal_safety, /analyze_safety).
- Veri akışı: formlar currentResults'tan otomatik dolar AMA bağımsız da çalışır; POST her zaman formdan.
- Dosya sahipliği (paralel ajan kuralı): dock ayrı ajan, paneller ayrı ajan, 3 şablon TEK ajan.

### Dalga 2 — Performans + PDF + göç
- `performance_panel.js`: /api/advanced-performance-analysis'in 3 hazır Plotly çıktısı (Pc-O/F-Isp yüzeyi, Mach konturu, ısı akısı).
- Eksenel q(x)/Tw(x) profili: Bartz zaten area_ratio_local alıyor, nozul konturu mevcut — 30-50 istasyon.
- PDF rapora gerçek analiz bölümleri (pdf_generator'ın analysis_results iskeleti hazır).
- Hibrit safety-tabs (advanced.html:1867) dock'a taşınır (çatallanma bitmeden katı/sıvı Dalga 1'de dock'tan alır).

### Dalga 3 — Yeni fizik modülleri (kapsam ARGE'sinin reçeteleri, hepsi literatür referanslı)
- `pressure_vessel.py`: ASME VIII UG-27/32/99 + AIAA S-080 **mod seçimli** (varsayılan S-080) + **Faupel kopma basıncı** ("bu tank kaç barda patlar" tek bakışta kırmızı/yeşil).
- `thermal_protection.py`: ablasyon Seviye 1 (Q* modeli, NASA SP-8091 sınıfı kaynaklı sabitler) + 1D transient heat-sink çözücü (~80 satır explicit FD — kısa yanmada denge modeli fazla karamsar).
- Boğaz erozyonu: ampirik ṙ=a·(Pc/Pc_ref)^0.8 + transient_ballistics coupling (Pc/F eğrisine kayma).
- `bolted_joint.py`: ön-yük, tork (K=0.15/0.20, ±%25 beyanlı), ayrılma kontrolü.
- Yorulma: Goodman düzeltmesi (mevcut b=10 sabiti ve genlik=ortalama hatası düzeltilir).
- ANSYS sınırı beyanı UI'da: el hesabı kapsamı vs "ANSYS'e git" listesi (süreksizlik gerilmeleri, t/r>0.2, çok modlu slosh...).

### Dalga 4 — Akış, uzun koşumlar, doğrulama
*(2026-07-14 revizyonu — Berke'nin GPT-5.6 danışması ARGE öneri­siyle örtüştü; şu eklemeler kabul edildi:)*
- `nozzle_flow_1d.py` (CFD'nin yerine): quasi-1D sıkıştırılabilir akış + boğulma + Mach/P dağılımı + **under/over-expanded durumlar + nozul ayrılma (separation) kriteri (Summerfield)** + eksenel Bartz + temel viskoz kayıplar.
- Kinetik: **kademeli mimari** — equilibrium → frozen → basitleştirilmiş finite-rate → detaylı; hızlı taramada equilibrium/frozen, finite-rate için kendi integratörümüz DEĞİL **Cantera backend** (kuruluysa; yoksa η_kin korelasyonuna düş).
- UI seviye adlandırması: **Fast Screening / Engineering Fidelity / High-Fidelity Validation** (teknik modül adları yerine).
- MDO (çok disiplinli optimizasyon) bilinçli olarak kapsam DIŞI — ayrı gelecek dalga.
- `job_runner.py`: threading iş kuyruğu + progress (uzun analizler; Celery gereksiz).
- Deneysel doğrulama: **kullanıcı CSV modu** (sentetik DB vitrine çıkmaz; Berke kendi static-fire verisiyle karşılaştırır).
- /api/comparative-analysis şema doğrulaması + panel; /api/professional-analysis emekli.
- Sıvı: rejeneratif soğutma 1D istasyon-marş modeli (büyük parça); slosh SP-106 (bağımsız rapor), su koçu (Joukowsky), basınçlandırıcı gaz boyutlandırma (küçükler).

### Tema dalgası (#8 — analiz dalgalarına paralel yürüyebilir, dosyaları ayrık)
- Yeni katman: `results_hud.css` (~250 satır) + `hud.js` (~80 satır) — theme.css'e DOKUNULMAZ.
- Bileşenler (hepsi prototipte doğrulandı — scratchpad/hud_prototype.html): durum LED'i + statustag (yalnız UNSAFE'te blink), NSA-tarzı rapor başlığı + Bloomberg özet şeridi (tabular-nums), count-up metrik kartları + sparkline + delta, terminal log (v1 playback — gerçek sayılarla), 5×5 CSS-grid risk matrisi, tek atışlık tarama süpürmesi.
- `plotly_dark.js`'e 5 merkezi ek: colorway, spike crosshair, modebar teması, mono tick font, koşullu unified hover.
- `displayPerformanceMetrics`'teki eski mor gradyan kartlar hd-metric'e geçer.
- **Kitsch sınırları (7 kural):** sahte veri yasak, en fazla 2 kalıcı animasyon, kırmızı semantiktir, köşe krokileri yalnız üst konteynerde, veri yüzeyine süs binmez, grafikte sonradan hareket yok, ses yok; prefers-reduced-motion desteklenir.

## Açık kararlar (Berke)
1. **CFD + kinetik:** yeniden-yazım yerine gerçekçi hızlı modellerle değiştirme (öneri) — onay?
2. Başlangıç kapsamı: Dalga 0+1 hemen mi, tema dalgası da paralel mi?
