# Ne Yapar — Ölçülmüş Yetenek Envanteri

**Son güncelleme: 2026-08-14**
**Kapsam:** HRMA'nın gerçekten sahip olduğu hesap yetenekleri, analiz
modülleri ve çıktı biçimleri. Her satır depoda ölçülmüştür; ölçülemeyen
hiçbir yetenek buraya yazılmamıştır. Kapsam dışı olanlar için
[ne-yapmaz.md](ne-yapmaz.md), geçerlilik sınırları için
[gecerlilik-zarfi.md](gecerlilik-zarfi.md).

**Ölçüm tabanı:** `2e2375d`.

---

## 1. Motor aileleri

HRMA üç motor ailesini çözer. Her ailenin kendi çözücü sınıfı vardır:

| Aile | Çözücü sınıfı | Konum |
|---|---|---|
| Hibrit | `HybridRocketEngine` | `hrma/engines/hybrid_rocket_engine.py:429` |
| Katı | `SolidRocketEngine` | `hrma/engines/solid_rocket_engine.py:860` |
| Sıvı | `LiquidRocketEngine` | `hrma/engines/liquid_rocket_engine.py:909` |

Ortak destek modülleri: `combustion_analysis.py` (denge termokimyası,
`CombustionAnalyzer:72`), `nozzle_design.py` (`NozzleDesigner:14`),
`injector_design.py`, `cycle_power_balance.py` (sıvı çevrim güç dengesi),
`cea_bridge.py` (basınca bağımlı yanma verisi köprüsü).

### Yakıt/oksitleyici kapsamı

Hibrit regresyon katsayısı tablosunda **9 kayıt** vardır
(`hrma/data/propellant_database.py:31`). Bunlardan **beşi** hakemli
yayından alınmış künyeli korelasyondur (`htpb`, `paraffin`, `pe`, `pmma`,
`abs` — Doran AIAA 2007-5352, Karabeyoglu 2004, Zilliac & Karabeyoglu
AIAA 2006-4504, Whitmore & Peterson 2013). Kalan **dördü** (`pla`,
`carbon`, `aluminum`, `al2o3`) dosyanın kendi ifadesiyle *"yayınlanmış,
hakemli bir korelasyon bulunamadı; önceki kod değerleri DOĞRULANMAMIŞ
olarak korunur (tasarım için kullanmayın)"* notunu taşır
(`propellant_database.py:48-53`). Bu ayrım kullanıcıya aynen geçer;
katsayının kaynaklı olup olmaması bir tercih değil, kayıt altındaki bir
farktır.

Katı yakıt yanma hızı yasaları merkezî `hrma/data/burn_rate_db.py`
dosyasındadır (`BURN_RATE_LAWS`), birim ve kaynak alanlarıyla birlikte.

---

## 2. Analiz modülleri

`hrma/analysis/` altında **32 modül** ölçüldü (`__init__.py` hariç).
Aşağıdaki tablo her modülün kendi docstring'inde beyan ettiği kapsamı verir.

| Modül | Ne hesaplar |
|---|---|
| `acoustic_modes.py` | Silindirik hazne akustik mod frekansları ve marj |
| `bolted_joint.py` | Cıvatalı flanş/kapak bağlantısı (Shigley yöntemi) |
| `curve_sampling.py` | Yayımlanan zaman serilerinin tepeyi koruyan seyreltmesi |
| `flight_vehicle.py` | Uçuş aracı geometri/kütle girdisi doğrulaması |
| `gimbal_mount.py` | Gimbal montaj ve aktüatör *yük* çözümü (TVC) |
| `heat_transfer_analysis.py` | Hazne cidar sıcaklığı, Bartz ısı akısı, Leckner gaz ışınımı |
| `igniter_sizing.py` | Torç ve piroteknik ateşleyici enerji/debi boyutlandırması |
| `kinetic_analysis.py` | Lüle kinetik kaybı (eski katman) |
| `kinetic_efficiency.py` | Kademeli lüle kinetik verimi (yukarıdakinin halefi) |
| `launch_site.py` | Konum → rakım → atmosfer → yerel yerçekimi zinciri |
| `nozzle_flow_1d.py` | Yarı-1B sıkıştırılabilir lüle akışı (sahte CFD panelinin halefi) |
| `pressurant_sizing.py` | Regüleli ve blowdown besleme için basınçlandırma gazı |
| `pressure_vessel.py` | Basınçlı kap boyutlandırma ve kopma basıncı |
| `regen_cooling.py` | 1B istasyon-yürüyüşlü rejeneratif soğutma |
| `regression_analysis.py` | Hibrit yakıt regresyon hızı analizi |
| `safety_analysis.py` | Kapsamlı tehlike/risk değerlendirme raporu |
| `safety_limits.py` | Model girdisi akıl sağlığı sınırları (**emniyet kapısı değildir**) |
| `six_dof_trajectory.py` | 6 serbestlik dereceli rijit gövde uçuş dinamiği |
| `slosh_analysis.py` | Dik silindirik tankta yakıt çalkalanması |
| `structural_analysis.py` | Cidar kalınlığı, gerilme ve emniyet katsayısı |
| `tank_blowdown.py` | N₂O kendinden basınçlı tank blowdown |
| `thermal_protection.py` | Ablatif / ısı yutucu / ışınımla soğutmalı termal koruma |
| `tile_cache.py` | NASA GIBS uydu karo getirici ve disk önbelleği |
| `trajectory_analysis.py` | Nokta-kütle uçuş yörüngesi |
| `transient_ballistics.py` | Zaman çözümlü iç balistik: Pc(t), F(t) |
| `turbopump_sizing.py` | Turbopompa boyutlandırma (tek tasarım noktası) |
| `two_phase_loss.py` | Katı motorda tanecikli akış Isp kaybı kestirimi |
| `uncertainty.py` + `uq_adapters.py` | Monte Carlo belirsizlik nicelemesi |
| `valve_feedline.py` | Vana kapasitesi ve besleme hattı basınç bütçesi |
| `water_hammer.py` | Besleme hattı su koçu geçici basıncı |
| `cfd_analysis.py` | **Emekli** — uç noktası 501 döner, bkz. [ne-yapmaz.md](ne-yapmaz.md) |

### FEA çekirdeği

`hrma/fea/` altında eksenel simetrik sonlu eleman çözücüleri vardır. Paket,
hangi çözücünün gerçekten uygulandığını makine okunur biçimde beyan eder
(`hrma/fea/__init__.py`, `MODULE_STATUS`):

| Çözücü | Durum |
|---|---|
| `mesh_axisym` — (z, r) quad mesh üreticisi | `IMPLEMENTED` |
| `structural_axisym` — lineer elastik çözücü + yakınsama sürücüsü | `IMPLEMENTED` |
| `thermal_axisym` — geçici ısı iletimi (geri Euler, Bartz konveksiyon BC) | `IMPLEMENTED` |
| `planar_grain` — katı yakıt tanesi 2B düzlemsel kip | `NOT_IMPLEMENTED` |

Harici mesh bağımlılığı (gmsh vb.) yoktur; `numpy` + `scipy.sparse`
yeterlidir. HTTP uçları: `/api/fea/structural` (`hrma/app.py:7265`) ve
`/api/fea/thermal` (`hrma/app.py:7502`).

> **Not:** Kök `README.md`, FEA çekirdeğinden özellik listesinde hiç söz
> etmez. Modül mevcut ve HTTP'den erişilebilirdir; README bu noktada
> yeteneği eksik anlatmaktadır.

### Yarı-1B akış çekirdeği

`hrma/flow/` iki modül taşır: `quasi1d.py` (rejim sınıflandırması,
izantropik dallar, lüle içi normal şok konumu — Anderson, *Modern
Compressible Flow*, 3. baskı) ve `separation.py` (Summerfield / Schmucker /
Kalt-Badal ayrılma kriterleri, geçerlilik aralıkları beyanlı). Her ikisi de
modellemediklerini paket düzeyinde ilan eder (`QUASI1D_NOT_MODELLED`,
`SEPARATION_NOT_MODELLED`).

---

## 3. Malzeme ve veri tabanları

- **Malzeme veri tabanı:** `hrma/data/materials_db.py:85` içindeki
  `MATERIALS` sözlüğünde **24 kayıt** ölçüldü (çelikler, paslanmazlar,
  alüminyum alaşımları, titanyum, Inconel 718/625, bakır ve CuCrZr,
  molibden TZM, tungsten, niyobyum C-103, grafit, karbon-karbon, ablatif
  astar, berilyum bakır, pirinç, magnezyum). Sıcaklığa göre azaltılmış
  özellikler yapısal ve termal panelleri besler.
- **Yakıt veri tabanı:** `propellant_database.py`, `propellants_db.py`,
  `burn_rate_db.py`, `chemical_database.py`.
- **Gerçek deney veri tabanı:** `hrma/data/validation_records/` altında
  git ile izlenen, künyeli statik ateşleme kayıtları. `inputs` ve
  `measured` alanları yapısal olarak ayrıdır; bu ayrım, ölçülen bir
  değerin modele girdi olarak verilip sonra "tahmin" diye raporlanmasını
  (dairesel doğrulama) engeller.

---

## 4. HTTP yüzeyi

`hrma/app.py` içinde **91 rota** ölçüldü (`grep -c "@app.route"`). Başlıca
öbekler:

| Öbek | Örnek uçlar |
|---|---|
| Motor çözümü | `/calculate`, `/calculate_solid`, `/calculate_liquid`, `/api/quick-geometry` |
| Zaman çözümlü | `/api/transient-analysis`, `/api/six-dof-analysis`, `/api/trajectory-analysis` |
| Yapı ve termal | `/analyze_structural_safety`, `/analyze_thermal_safety`, `/api/analysis/wall-profile`, `/api/pressure-vessel-analysis`, `/api/bolted-joint`, `/api/analysis/thermal-protection` |
| Akış | `/api/flow-analysis` (yarı-1B), `/api/kinetic-efficiency`, `/api/kinetic-analysis` |
| FEA | `/api/fea/structural`, `/api/fea/thermal` |
| Besleme sistemi | `/api/regen-cooling`, `/api/slosh-analysis`, `/api/pressurant-sizing`, `/api/water-hammer`, `/api/injector-design` |
| Belirsizlik ve doğrulama | `/api/uncertainty-analysis`, `/api/solid-monte-carlo`, `/api/correlation-report`, `/api/validation/upload-csv` |
| Dışa aktarım | `/api/export-step`, `/api/export-dxf`, `/api/export-stl-zip`, `/api/export-drawings-pdf`, `/api/export-eng`, `/api/export-xlsx`, `/api/export-complete-zip` |
| Fırlatma sahası | `/api/launch-site/resolve`, `/api/tile/<layer_key>/<z>/<x>/<y>` |

> **Not:** Kök `README.md` proje yapısı bölümünde `app.py` için
> "~73 routes" yazar. Ölçüm 91'dir; README bu noktada eskimiştir.

---

## 5. Çıktı biçimleri

Ölçülen dışa aktarım yolları (rota referanslarıyla):

| Biçim | Uç nokta |
|---|---|
| STL (katı gövde, revolve edilmiş gerçek lüle konturundan) | `/api/export-stl`, `/api/export-stl-zip` |
| STEP (parametrik katı, build123d/OpenCascade) | `/api/export-step` |
| DXF (katmanlı imalat profili, ezdxf) | `/api/export-dxf` |
| Teknik resim PDF (çok sayfalı, ölçülendirilmiş) | `/api/export-drawings-pdf` |
| Rapor PDF | `/api/export-pdf/<report_type>`, `/api/export-chart-pdf` |
| OpenRocket `.eng` (gerçek hesaplanan itki eğrisi) | `/api/export-eng`, `/api/export-openrocket` |
| XLSX | `/api/export-xlsx` |
| Tam paket ZIP (STL+STEP+DXF+PDF+.eng+geometri) | `/api/export-complete-zip`, `/api/generate-complete-package` |

---

## 6. Belirsizlik nicelemesi

`hrma/analysis/uncertainty.py` üç açık çaba seviyesi tanımlar
(`uncertainty.py:63-65`): `fast` = 200, `engineering` = 1000,
`high_fidelity` = 3000 örnek. Latin Hiperküp örneklemesi kullanılır; her
çıktı P50 medyan ve [P5, P95] aralığı olarak raporlanır, girdi
duyarlılıkları Spearman sıra korelasyonuyla sıralanır. Tohum sabittir,
sonuç yeniden üretilebilir. Uç: `/api/uncertainty-analysis`.

---

## 7. Doğrulama altyapısı

- **Kod-koda doğrulama:** Termokimya NASA CEA'ya (RocketCEA üzerinden),
  gaz dinamiği kapalı form Sutton & Biblarz bağıntılarına karşı
  kıyaslanır.
- **Gerçek veriye karşı doğrulama:** `hrma/validation/correlation_runner.py`
  deney veri tabanını tarar ve `docs/VALIDATION_STATUS.md` içindeki
  `AUTO-CORRELATION` bloğunu makine üretimiyle doldurur. Blok elle
  düzenlenmez; bir bekçi testi korelasyonu yeniden koşup blok bugünkü
  kodun ürettiğinden saparsa kırmızıya döner. Blok bir kez 9 gün bayat
  kalmıştır; bekçi testi bu yüzden vardır.
- **Sayıları buradan tekrarlamıyoruz.** Güncel sapma, medyan mutlak yüzde
  hata ve örnek sayıları için doğrudan
  [`docs/VALIDATION_STATUS.md`](../VALIDATION_STATUS.md) okunmalıdır;
  belge hangi commit ve hangi koşucu sürümüyle üretildiğini kendi
  künyesinde söyler.
- **Kaynak künyesi:** Kullanılan standartların tam adı ve doğrulanma
  durumu [`docs/STANDART_ATIFLARI.md`](../STANDART_ATIFLARI.md)
  defterindedir. `tools/iddia_lint.py` bilinen yanlış başlıkları makinece
  yakalar.

---

## 8. Test yüzeyi

Ölçüm: `tests/` altında **219 test dosyası** ve **4 865 test fonksiyonu**.
Süit her push'ta GitHub Actions üzerinde koşar.

```bash
MPLBACKEND=Agg PYTHONPATH=. pytest tests/ -q
```

> **Not:** Kök `README.md` "1,000+ automated tests" der. Ölçülen sayı çok
> daha yüksektir; iddia yanlış değil ama güncelliğini yitirmiştir.

---

## 9. Uygulama biçimi

- Yerel Flask sunucusu (`hrma/run.py`, waitress, 8080–8090 arası boş port
  taraması).
- Kendi penceresinde açılan masaüstü uygulaması (macOS WKWebView /
  Windows WebView2).
- Çevrimdışı çalışır: Plotly, Three.js ve MathJax paketin içindedir, CDN
  bağımlılığı yoktur.
- Arayüz Türkçe ve İngilizce (`hrma/static/js/i18n_*.js`).
- Analiz güvertesi: `hrma/static/js/panels/` altında **14 panel** dosyası
  ve ayrıca `injector_panel.js`; hepsi `hrma/templates/advanced.html:716-741`
  içinde yüklenir.

> **Not:** Kök `README.md` "Analysis Deck (13 panels)" der ve 13 panel
> sayar; ölçülen güverte 15 paneldir (14 + enjektör). README'nin listesi
> belirsizlik ve korelasyon panellerini güverte üyesi olarak saymaz.
