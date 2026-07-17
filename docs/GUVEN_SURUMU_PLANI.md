# HRMA v2.5.0 — Güven Sürümü Planı

Durum 2026-07-17: ARGE turu tamamlandı (4 ajan), plan Berke onayı bekliyor.
ARGE tasarım dokümanları: `docs/arge-guven-2026-07/` (UQ mimarisi, hibrit veri,
katı/sıvı veri, korelasyon altyapısı). Kaynak PDF arşivi (telif nedeniyle repo
dışı): `~/Desktop/dosyalar/HRMA-dogrulama-kaynaklari/`.

## Hedef

Bir NASA/SpaceX motor mühendisinin **ön tasarım aracı olarak gönüllü
kullanacağı** güvenilirlik. İki ayak:

1. **Belirsizlik nicelemesi (UQ):** nokta tahmin yerine güven aralığı —
   "Isp = 229.4 s" değil "229.4 s, P5-P95: 223-236 s" + duyarlılık sıralaması.
2. **Gerçek deney doğrulaması:** açık literatürdeki static-fire/motor
   verisinden künyeli doğrulama veritabanı + otomatik korelasyon raporu +
   pytest regresyon bekçisi.

## ARGE bulgularının özeti

### UQ (arge_uq_tasarim.md)
- Altyapının çoğu hazır: katıda seed'li `run_monte_carlo`, `job_runner`,
  üç kademeli fidelity kalıbı, `eta_c_star` parametresi.
- Ölçülen tek-hesap süreleri (M4 Max): katı 3.2 ms, sıvı 0.4 ms, hibrit
  1037 ms → `uq_mode` (opsiyonel O/F araması atlanır) + denge memoizasyonu
  ile hibrit örneği 91-185 ms.
- Örnek bütçeleri: hibrit Fast 200 (~20-30 s) / Engineering 1000 (~1.5-3 dk) /
  High-Fidelity 3000 (~9-14 dk, job_runner + progress); katı/sıvı saniyeler.
- Girdi dağılımları literatür künyeli: λ_r ~ N(1, 0.15) regresyon çarpanı
  (Chiaverini & Kuo 2007; Karabeyoglu 2004; Zilliac AIAA 2006-4504),
  n ± 0.03, η_c* ~ N(0.93, 0.03) (Sutton 9. baskı), Cd ~ N(0.70, 0.05)
  (Dyer NHNE ± %15), yoğunluk ± %2, Pc ± %2.
- LHS: `scipy.stats.qmc` (kurulu 1.13.1) — YENİ BAĞIMLILIK YOK.
- Duyarlılık: Spearman + tornado (MC örneklerinden bedava). Sobol v2.6'ya.
- Omurga garanti: her koşuda örnek #0 = nominal vektör, deterministik
  sonuçla 1e-9 eşleşme zorunlu; MC nominali asla değiştirmez.
- Kritik yan bulgu: sıvı motor kurucusu her çağrıda CANLI HTTP isteği
  yapıyor (0.66 s) — MC öncesi veri bir kez çekilip enjekte edilmeli
  (çevrimdışı ilkesiyle de uyumlu).

### Hibrit deney verisi (arge_hibrit_veri.md)
- 9 kampanya, ~135 gerçek test noktası; tüm sayılar kaynak PDF'lerden
  doğrudan okundu (high confidence), ikincil atıf yok.
- İlk korelasyon hedefi: 69 motor-düzeyi nokta + Whitmore 32-yakma
  istatistik seti (dağılım düzeyinde, mu/sigma).
- En güçlü 5: Rezaei 2018 HTPB/N2O (31 test), Karabeyoglu AIAA 2003-1162
  parafin/GOX (26 satır), Whitmore & Stoddard 2020 GOX+Nytrox/ABS,
  Wei 2025 PP/N2O blowdown (transient modülü için birebir),
  Hansen 2012 uçuş ölçeği parafin-HTPB/N2O blowdown.
- Dürüstlük kayıtları: Whitmore Nytrox c* baskı hatası (560.84 → 1560.84,
  `source_erratum` ile), McFarland 2019 karantinada (oksitleyici türü
  belirsiz, yazar teyidi bekliyor).
- Erişim engelli (tarayıcıyla manuel indirme listesi dosyada): USU
  DigitalCommons (Whitmore Deep Throttle), AIAA ARC (Lohner 2006-4671,
  McCormick 2003-6475 — parafin/N2O birincil a-n kaynağı).

### Katı/sıvı veri (arge_kati_sivi_veri.md)
- Katı: Nakka KNDX/KNSB strand verisi (27 nokta + rejimli a-n tabloları),
  KNSU ölçülmüş c*, DSC 6-motor KNSB statik seti. APCP çapası AÇIK:
  TAMU/MIT kaynakları bot korumalı, tarayıcıyla indirilmeli.
- Sıvı 6 motor çapası (birincil belgelerden): RL10A-3-3A (5 ölçülmüş test
  noktasıyla), RS-25, F-1, J-2, Vulcain 2.1, Merlin 1D (yalnız resmi itki).
  J-2'nin iki MR noktası Isp(MR) eğim doğrulaması fırsatı.
- Kabul bandı önerileri: sıvı Isp ± %2 (ideal) / ± %4 (ROCETS emsali),
  katı r(P) ± %10.

### Korelasyon altyapısı (arge_korelasyon_tasarim.md)
- Mevcut envanter: 11 SENTETİK kayıt (sinüs+gürültü) SQLite'ta;
  `user_data_validation.py` (Dalga 4A) eğri karşılaştırma çekirdeği olarak
  yeniden kullanılabilir. YAN BULGU: `/api/experimental-validation` ölü
  endpoint (sınıfta var olmayan metotları çağırıyor → 500).
- Tasarım: git-izlenen JSON kayıtları (SQLite emekli), `inputs`/`measured`
  ayrımıyla döngüsellik bekçisi, 3 kademeli confidence, adapter'lı
  korelasyon koşucusu (bias/RMS/medyan APE, 3xMAD aykırı işaretleme),
  VALIDATION_STATUS.md otomatik bölge, correlation paneli, paper-kalite
  rapor, iki katmanlı pytest bekçisi (fizik tavanı + baseline×1.25 +
  aşırı-iyileşme uyarısı), UQ entegrasyonu (ASME V&V 20 E_n) son dalgada.

## Dalga planı (geliştirme, onay sonrası)

Sıralama dosya-çakışması gözetilerek; her dalga sonunda tam test + commit.

- **G1 — Çekirdekler (2 paralel ajan, dosya ayrık):**
  (a) UQ çekirdeği: `hrma/analysis/uncertainty.py` (LHS, dağılım modeli,
  seed, örnek-#0 garantisi) + hibrit `uq_mode`/memoizasyon;
  (b) Deney DB temeli: JSON şema + kayıt deposu, sentetik kayıtların
  fikstüre taşınması, SQLite ve ölü endpoint sökümü.
- **G2 — Veri küratörlüğü + koşucu:** ARGE tablolarından JSON kayıtlarının
  yazılması (69 hibrit + Nakka seti + 6 sıvı çapa; her kayıt künyeli),
  korelasyon koşucusu + adapter'lar.
- **G3 — API + UI:** `/api/uncertainty-analysis` + UNCERTAINTY paneli
  (histogram, tornado, CI kartları), correlation paneli,
  VALIDATION_STATUS.md otomatik üretim.
- **G4 — Bekçiler + rapor + yayın:** pytest korelasyon bekçileri,
  paper-kalite korelasyon raporu, README/USER_MANUAL güncellemesi,
  v2.5.0 derleme + release.

Kaba efor: UQ ~1500-1900 satır; korelasyon ~4.5-5.5 ajan-günü; toplam
3-4 çalışma oturumu.

## Berke onayı bekleyen kararlar (öneriler işaretli)

1. **Sentetik 11 kayıt** → üretimden sök, `tests/fixtures`'a taşı
   (synthetic:true; istatistik/UI/rapora girmesi yapısal olarak imkansız).
   ÖNERİ: evet.
2. **Nakka KN-şeker + thrustcurve.org verisi** DB'ye girsin mi? ÖNERİ:
   evet, kaynak rozetiyle; ana istatistik high+medium üstünden, low ayrı.
3. **APCP kaynakları**: TAMU tezi + MIT makalesi + USU/AIAA PDF'leri
   tarayıcıyla manuel indirilecek (liste ARGE dosyalarında). Berke'nin
   10 dakikalık tarayıcı işi — yapılana kadar APCP çapası pasif.
4. **Bekçi eşikleri**: c* medyan APE %5, teslim Isp %10, hibrit regresyon
   %35, toplam impuls %10 + baseline×1.25 kuralı. ÖNERİ: kabul, ilk
   korelasyon koşusundan sonra gözden geçir.
5. **Hibrit High-Fidelity MC bütçesi**: 3000 örnek ≈ 9-14 dk (job_runner
   arkasında). ÖNERİ: kabul.
6. **Sıvı kurucudaki canlı HTTP'nin kaldırılması** (veri bir kez çekilip
   enjekte edilir). ÖNERİ: kesinlikle v2.5.0'a girsin — çevrimdışı
   ilkesinin devamı.
7. **Eğri sayısallaştırma** (WebPlotDigitizer, ± %2 ek belirsizlik,
   'digitized' etiketiyle): katı p-t eğrileri için. ÖNERİ: dahil.

## Riskler (ARGE'den birleştirilmiş)

- Veri küratörlüğü darboğaz: paywall'lı kaynaklar manuel indirme istiyor;
  APCP kapanmazsa katı doğrulama KN-şekerle sınırlı kalır.
- MC süreleri M-serisi ölçümü; eski Windows donanımında 2-3x yavaş
  (seviye etiketlerinde pay bırakıldı).
- Döngüsellik kaçağı (ölçümün girdiye sızması) küratör disiplini ister;
  şema ayrımı + aşırı-iyileşme uyarısı yakalamak için tasarlandı.
- Arıza etiketli testler (lüle erozyonu vb.) filtrelenmeden korelasyona
  girerse sapma yaratır — şemada `anomaly` alanı zorunlu.
