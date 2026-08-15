# Geçerlilik Zarfı ve `NOT_MODELLED` Disiplini

**Son güncelleme: 2026-08-15**
**Kapsam:** Her analiz modülünün geçerli olduğu aralık, zarf dışına
çıkıldığında yazılımın ne yaptığı, ve bu davranışın kodda nasıl uygulandığı.
Bu belge HRMA'nın en ayırt edici disiplinini anlatır: **model kendi
zarfının dışına çıktığında sayı üretmez, beyan üretir.**

**Ölçüm tabanı:** `2e2375d`.

---

## 1. Sözleşme

Bir HRMA modülü bir büyüklüğü hesaplayamadığında üç şeyi birden yapar:

1. **Sayı yerine `null` koyar.** Sıfır, varsayılan veya "makul" bir
   literatür değeri konmaz.
2. **Bir durum alanı doldurur:** `status`, `thickness_status`,
   `mass_status`, `burn_time_status`, `descent_model`,
   `joint_reliability_status`, `manufacturing_tolerance_status` gibi. Değer
   `NOT_MODELLED` olur.
3. **Gerekçeyi yazar:** `basis` / `_basis` / `reason` / `missing_inputs`
   alanlarında, *neyin eksik olduğunu adıyla* söyler.

Ölçüm: `NOT_MODELLED` dizgesi `hrma/` ağacında **214 yerde** geçer —
Python tarafında 19 dosyada 209 geçiş, arayüz tarafında 5 geçiş. Ayrıca
`tests/` altında 166 gönderme vardır: disiplin testlerle korunur, iyi
niyete bırakılmaz.

Aynı ailede kardeş durumlar da vardır; hepsi "sayı yok, gerekçe var"
sözleşmesinin farklı sebeplerini adlandırır:

| Durum | Anlamı | Örnek |
|---|---|---|
| `NOT_MODELLED` | Modelin bu büyüklüğü üretecek temeli yok | `hrma/engines/solid_rocket_engine.py:6040` |
| `not_analyzed` | Girdi eksik/geçersiz, rapor üretilmedi | `hrma/utils/injector_design.py:1184` |
| `NOT_EVALUATED` | Hiç kontrol koşmadı (uygunluk, emniyet) | `hrma/analysis/safety_analysis.py:1201` |
| `no_published_data` | Katsayı için yayımlanmış kaynak yok | `hrma/engines/hybrid_rocket_engine.py:1298` |
| `NOT_IMPLEMENTED` | Çözücü henüz yazılmadı | `hrma/fea/__init__.py` (`planar_grain`) |

---

## 2. `NOT_MODELLED` neden çıkar — sekiz grup

Aşağıdaki gruplar depodaki gerçek örneklerden çıkarılmıştır.

### Grup 1 — Girdi eksik: sayı uydurulmaz, eksik girdinin **adı** söylenir

| Örnek | Konum |
|---|---|
| Su koçu geçici basıncı: besleme hattı cidar kalınlığı verilmemiş | `hrma/engines/liquid_rocket_engine.py:6913` |
| NPSH zinciri: itici buhar basıncı tabloda yok ("hiçbir şey uydurulmaz") | `liquid_rocket_engine.py:7082` |
| Türbin geometrisi: türbin gücü ve debisi pozitif değil | `liquid_rocket_engine.py:7207` |
| Termal koruma: Bartz ısı akıları / sıcak cidar sıcaklığı / pozitif yanma süresi eksik | `liquid_rocket_engine.py:9130` |
| İki fazlı Isp kaybı: çözücü gerekli alanları üretmiyor | `hrma/engines/solid_rocket_engine.py:3960` |
| Akustik mod tablosu: kavite geometrisi veya gaz hâli varsayılmaz | `solid_rocket_engine.py:4106` |
| Yapısal termal yol: gaz veya cidar sıcaklığı verilmemiş | `hrma/app.py:6557-6565` |
| FEA köprüsü: girdi eksikse `status='NOT_MODELLED'` + `missing` listesi | `hrma/fea/bridge.py:162, 477` |

### Grup 2 — Fiziksel olay modelin kapsamı dışında (modül düzeyinde beyan)

Bu modüller, **her sonuçta** modellemediklerini bir sözlük olarak yayımlar:

| Modül | Beyan | Kalem |
|---|---|---|
| `valve_feedline.py:290` | `NOT_MODELLED` | 10 |
| `gimbal_mount.py:132` | `NOT_MODELLED` | 9 |
| `igniter_sizing.py:151` | `NOT_MODELLED` | 9 |
| `turbopump_sizing.py:227` | `NOT_MODELLED` | 6 |
| `flow/separation.py:101` | `SEPARATION_NOT_MODELLED` | 5 |
| `flow/quasi1d.py:123` | `QUASI1D_NOT_MODELLED` | 4 |
| `two_phase_loss.py:181` | `NOT_MODELLED` | 4 |
| `acoustic_modes.py:134` | `NOT_MODELLED` | 3 |
| `launch_site.py:108` | `NOT_MODELLED` | 3 |

Kalemlerin içeriği [ne-yapmaz.md](ne-yapmaz.md) belgesinde madde madde
verilmiştir.

### Grup 3 — Geçerlilik zarfı ihlali: model koşar, kapı sayıyı reddeder

En sert biçim budur: hesap tamamlanır, ama sonuç modelin varsayım
zarfının dışına düştüğü için **yayımlanmaz**.

- **Ablasyon gerileme hızı tavanı.** Termal koruma modülü kendi geçerlilik
  tavanını `RECESSION_VALID_MAX_MM_S` sabitinde ilan eder
  (`hrma/analysis/thermal_protection.py`, ölçüm anında satır 145 —
  *modül etkin geliştirme altındadır, satır numarası yerine sabit adını
  arayın*). Modülün gerekçesi: bu hızın üstünde çıkan bir sonuç *ölçülmüş
  hiçbir ablatif çalışma noktasına karşılık gelmez* ve yarı-kararlı Q\* +
  sabit yüzey sıcaklığı varsayımlarının dışındadır. Kapı devreye girince
  `thickness_status='NOT_MODELLED'`, `model_valid=False` olur ve gerekçe
  `validity_note` alanına yazılır. Hüküm üç motora da **aynen taşınır**
  (hibrit/sıvı `_liner`, katı `_ablative_liner_sizing` — hepsi çekirdeğin
  `thickness_status` alanını değiştirmeden yayımlar).
- **Ablasyonda `no_net_heating` hükmü (2026-08-15).** Yüzey enerji
  dengesi, kurtarma sıcaklığı malzemenin yüzey sıcaklığının altında
  kaldığında gerilemeyi ~0 bulur. Bu durumda da kalınlık **yayımlanmaz**
  (`thickness_status='NOT_MODELLED'`): gerileme sıfır olsa bile astar
  kalınlığını kasa/bond hattı sıcaklık sınırı (iletim/char derinliği,
  NASA SP-8093 pratiği) belirler ve modül o iletim boyutlandırmasını
  modellemez. Eski davranış (0,0 mm + `sized`) sessiz tehlike sayılıp
  kaldırıldı. Üfleme blokajı da artık sabit bir katsayı değildir; B′
  üzerinden öz-tutarlı çözülür (`_solve_blown_surface_balance`) ve
  türetimi `blockage_basis` alanında beyan edilir.
- **Gimbal açısı.** Sert aralık `GIMBAL_ANGLE_VALID_DEG = (0.0, 45.0)`
  (`gimbal_mount.py:107`); dışına çıkan çağrı `ValueError` ile reddedilir
  (`gimbal_mount.py:212-220`).
- **Emiş özgül hızı hedefi.** `NSS_TARGET_VALID_US = (5000.0, 55000.0)`
  (`turbopump_sizing.py:146`, kontrol `:417`).
- **İki fazlı kayıp veri pencereleri.** `VALIDITY_RANGES`
  (`two_phase_loss.py:151`) beş büyüklük için kaynak künyeli pencere
  tanımlar: yoğuşmuş kütle oranı, hazne basıncı, boğaz çapı, tanecik çapı
  ve kalış süresi. Her pencerenin `source` alanı vardır (NASA SP-8039,
  Sutton & Biblarz 9. baskı §3.5, AIAA 96-2779). Pencere dışı girdi
  reddedilir; sonuç `_basis: 'validity guard'` künyesiyle döner
  (`two_phase_loss.py:517-577`).
- **Dittus-Boelter zarfı.** `DB_RE_MIN = 1.0e4`, `DB_PR_MIN/MAX = 0.6/160`,
  `DB_LD_MIN = 10` (`regen_cooling.py:325-330`). Zarf dışında korelasyon
  hâlâ bir sayı üretir, ama modülün kendi ifadesiyle *o sayının bildirilen
  ±%25 saçılımı geçerli değildir* — bu yüzden ihlal artık sessiz değil,
  `in_envelope=False` + `violations` listesiyle rapor edilir. Sieder-Tate
  düzeltmesinin uygulanmadığı da niceliksel olarak beyan edilir
  (`sieder_tate_correction_applied: False`).
- **Kriyojenik sıcaklık düşümü eğrisi.** Malzeme dayanım eğrileri yalnız
  yüksek sıcaklık için tanımlıdır (en düşük nokta tipik 20 °C).
  Kriyojenik çalışmada zarf dışına çıkılır; `below_curve_envelope`,
  `curve_min_temp_C` ve `is_cryogenic` alanları doldurulur ve `analyze()`
  bunlardan uyarı üretir (`pressure_vessel.py:165-200`, `:460`).
- **N₂O tank blowdown üst sınırı.** Kritik nokta `N2O_T_CRIT = 309.52 K`
  modelin üst geçerlilik sınırıdır (`tank_blowdown.py:45-46`); gömülü
  doygunluk verisinin zarfı dışına çıkıldığında `vapor_model_valid`
  bayrağı düşer (`tank_blowdown.py:407-408`, `:434`).
- **Ayrılma ölçütleri.** Summerfield / Schmucker / Kalt-Badal kriterleri
  kendi geçerlilik aralıklarıyla birlikte döner; aralık dışında
  değerlendirilen ölçüt `validity_warning` taşır
  (`flow/separation.py:119, 212-224, 405`) ve motor çıktısında
  `outside_validity_band` olarak görünür
  (`hrma/engines/hybrid_rocket_engine.py:4723`).

### Grup 4 — O akışkan/malzeme için model yok

- Kendinden basınçlı blowdown modeli **N₂O'ya özgüdür** (N₂O doygunluk
  tablosu / CoolProp N₂O EOS). Başka bir oksitleyici seçilirse blok
  `NOT_MODELLED` döner ve "bu oksitleyici için tank modeli yok" der
  (`hybrid_rocket_engine.py:2955`).
- Besleme akışkanı özellik tablosu belirli bir kümeyi kapsar; dışındaki
  itici için NPSH zinciri kurulmaz (`liquid_rocket_engine.py:7082`).
- **Tungsten erozyon katsayısı yayımlanmamıştır**, bu yüzden
  uydurulmaz: sonuç `status='no_published_data'` döner
  (`hybrid_rocket_engine.py:1193, 1298`; aynı politika
  `solid_rocket_engine.py:1169, 1186`). Grafit ve karbon-karbon için
  yayımlanmış bant vardır ve sayı üretilir.
- Hibrit regresyon tablosunda `pla`, `carbon`, `aluminum`, `al2o3`
  katsayıları "yayınlanmış, hakemli bir korelasyon bulunamadı …
  **tasarım için kullanmayın**" notuyla işaretlidir
  (`hrma/data/propellant_database.py:48-53`).

### Grup 5 — Bu koşuda hesaplanmadı (kip/anahtar kapalı)

- `track_performance` kapalıysa anlık performans geçmişi boştur;
  regüleli O/F(t), Isp(t) ve yanma-ortalamalı performans **hesaplanmaz ve
  kestirilmez** (`hybrid_rocket_engine.py:1974`, `:3189`).
- Belirsizlik kipinde (`uq_mode`) tavsiye nitelikli bloklar atlanır ve bu
  atlama beyan edilir (`hybrid_rocket_engine.py:2946`).
- Fırlatma rayı uzunluğu verilmediyse ray kısıtı ve yönelim dinamiği
  modellenmez (`trajectory_analysis.py:604`).

### Grup 6 — Çözücü hâli reddetti / yakınsamadı

- İki fazlı kayıp modülü çözücü hâlini reddetti → kayıp sayısı yok
  (`solid_rocket_engine.py:3981`).
- Akustik modül çözücü hâlini reddetti → mod tablosu yok (`:4129`).
- Yarı-1B çözücü yayımlanan lüle geometrisini reddetti → akış alanı yok
  (`:4301`); ayrılma modülü aynı biçimde (`:4332`).
- Blowdown çözücüsü ilk adımdan önce durdu → "yayımlanacak eğri yok"
  (`hybrid_rocket_engine.py:2999`).

### Grup 7 — Modül yüklenemedi

Bağımlılık eksikse blok sessizce boş dönmez; hangi modülün
yüklenemediğini söyler: `turbopump_sizing`
(`liquid_rocket_engine.py:7072`), `valve_feedline` (`:7249`),
`thermal protection` (`:9151`).

### Grup 8 — Uç nokta emekliye ayrıldı

`/api/cfd-analysis` HTTP 501 döner ve halef uç noktasını adıyla söyler
(`hrma/app.py:7770-7784`). Aynı disiplinin HTTP düzeyindeki karşılığıdır:
çalışmayan bir çözücü sessizce sayı üretmeye devam etmez.

---

## 3. Zarf dışına çıkınca ne olur — dört davranış

| Davranış | Ne zaman | Kullanıcı ne görür |
|---|---|---|
| `NOT_MODELLED` beyanı | Temel yok / girdi yok / kapı reddetti | Sayı yerine gerekçe ve eksik girdinin adı |
| `validity_warning` | Ölçüt aralık dışında ama sayı üretilebiliyor | Sayı **ve** aralık dışı uyarısı (`outside_validity_band`) |
| `model_valid=False` | Sonuç modelin varsayım zarfının dışında | Bayrak + `validity_note` gerekçesi |
| `ValueError` | Sert aralık ihlali (ör. gimbal açısı) | İstek reddedilir, aralık mesajda söylenir |

Hiçbir durumda `NaN` veya `∞` sayıya çevrilmez. v2.6.2 denetiminde
bulunan davranış — `NaN` → `0.0`, `∞` → `1e10` — kaldırılmıştır; bu
değerler artık `null` döner ve arayüzde tire olarak görünür.

---

## 4. Genel güvenilirlik zarfı

Aşağıdaki özet `docs/VALIDATION_STATUS.md` belgesinin "Reliability
envelope" ve "Known limitations" bölümlerinden çıkarılmıştır. **Sayıları
oradan okuyun**; bu belge onları tekrarlamaz, çünkü fizik değiştikçe
oradaki makine üretimi blok değişir.

| Güven düzeyi | Kapsam |
|---|---|
| Ön tasarım / ticaret çalışması için güvenilir | Gri yakıtlı hibrit ve sıvı performansı (c\*, Tc, ideal Isp) |
| Kalibrasyon veya bağımsız kontrolle kullanılır | Regresyon hızı, ısı yükü, yapısal marj, yörünge |
| Ateşleme öncesi **her hâlde** gerekir | Bağımsız çapraz kontrol (CEA / RPA / openMotor), hidrostatik basınç testi, ölçümlü yer ateşlemesi |

Belgede kayıtlı, ön tasarımda bilinmesi gereken model sınırlarından
bazıları:

- Hibrit regresyon hızı belirsizliği ampirik güç yasalarına ve parti
  değişkenliğine bağlı olarak geniştir; tek bir yayımlanmış a–n çifti
  bütün akı bandını temsil etmez.
- Sıvı **teslim edilen** Isp iyimser bir üst sınırdır: tablo CEA optimum
  genişleme değerini raporlar; gerçek motorlar sonlu genişleme oranı ve
  lüle kayıpları yüzünden daha düşük teslim eder.
- Küçük katı motorlar (yaklaşık 75 mm altı) fazla iyimser çıkar: iki
  fazlı akış, ısı kaybı ve kısa L\* ölçek etkileri modellenmez.
- Isı transferi Bartz tabanlıdır ve kendi saçılım bandını taşır; gerçek
  cidar sıcaklığı ve yanma-delinmesi marjı termokupl verisi ister.
- Yapısal marjlar konservatiftir, ama hidrostatik kanıt testinin yerine
  geçmez.
- Siyah barut / çift bazlı itici c\* değerleri bağımsız olarak
  çapalanmamıştır; yalnız gösterge niteliğindedir.

---

## 5. Bir çıktıyı okurken yapılacak dört kontrol

1. **`status` alanına bak.** `modelled` değilse, o blokta sayı yoktur —
   gerekçeyi oku.
2. **`_basis` / `basis` künyesini oku.** Sayının hangi bağıntıdan ve hangi
   kaynaktan geldiğini söyler (depoda 116 `_basis` künyesi ölçüldü).
3. **`validity_note` / `validity_warning` / `outside_validity_band`
   alanlarını ara.** Sayı üretilmiş olabilir ama zarf dışında olabilir.
4. **Uyarı panelini oku.** Motor tasarım uyarıları arayüze ulaşır; sessiz
   malzeme geri düşüşleri v2.6.26'da kapatılmıştır.
