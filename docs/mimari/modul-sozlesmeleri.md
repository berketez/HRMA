# Modül sözleşmeleri — katmanlar arasında neyin garanti edildiği

**Son güncelleme:** 2026-08-14
**Kapsam:** Katmanlar arası sözleşmeler. Bir analiz modülü ne alır, ne
döndürür; motor ile analiz sınırı nerededir; `NOT_MODELLED` beyanı ne
taahhüt eder; uç katmanı motordan neyi garanti ister. Katmanların ne
olduğu [sistem-haritasi.md](sistem-haritasi.md)'de, bir isteğin akışı
[veri-akisi.md](veri-akisi.md)'de.

**Ölçüm tabanı:** `2e2375d`, 14 Ağustos 2026.

---

## 0. Tek cümlelik özet

> Bu depoda bir sayı, **nereden geldiğini yanında taşımadan** hiçbir katman
> sınırını geçemez; modellenmeyen bir şey **modellenmediğini söylemeden**
> sessizce atlanamaz; ve her beyanın **onu okuyan bir kapısı** olmak
> zorundadır.

Üçüncü madde en pahalı derstir: Faz 4'te `_defaults_used` alanına **14 yerde
yazılıyor, 0 yerde okunuyordu.** Okunmayan beyan, beyan değildir.

---

## 1. Analiz modülü sözleşmesi (`hrma/analysis/*`)

### 1.1 Girdi

* **Anahtar kelimeli argüman zorunlu** (`def f(*, a, b)`). Sıraya bağlı
  çağrı, birim karışmasının en kolay yoludur.
* **SI birimi zorunlu**, ve birim **argüman adında** yazılır:
  `ignition_pressure_Pa`, `free_volume_m3`, `gas_temperature_K`,
  `density_kg_m3`, `line_pressure_drop_Pa`.
* Modül **motor sözlüğü almaz.** Ne `results`, ne `engine`, ne `self.motor`.
  Aldığı şey saf sayılar ve malzeme anahtarlarıdır.
* Modül **HTTP bilmez**, `request` okumaz, `jsonify` çağırmaz.

### 1.2 Çıktı

Düz bir `dict`. Ölçülmüş örnek —
`igniter_sizing.pyrotechnic_charge_mass(...)` 6 anahtar döndürür:

```
_basis                        → "Free-volume pressurisation criterion:
                                 m_gas = P_ign*V_free/(R*T_gas), ..."
charge_mass_kg                → 0.0026941007530067174
gas_mass_kg                   → 0.0016164604518040303
gas_mass_fraction             → 0.6
ignition_pressure_Pa          → 600000.0
specific_gas_constant_J_kg_K  → 296.9450935
```

Kural: **her sözlükte en az bir `_basis`.** `_basis`, sayının hangi
denklemden ve hangi kaynaktan çıktığını insan diliyle söyler; künye
(Sutton 9. baskı Böl. X, NASA SP-125 Böl. 6, Incropera §5.10 ...) modülün
üst blok belgesindedir.

### 1.3 Hata

Modül, fiziksel olarak imkânsız girdide **sessizce bir sayı üretmez**;
`ValueError` yükseltir ve mesaj **ne yapılacağını** söyler. Ölçülmüş örnek
(`turbopump_sizing.npsh_available_m`):

> `NPSH_available <= 0: pump inlet total pressure (… Pa after line loss) does
> not exceed the vapor pressure (… Pa); the pump would cavitate at the inlet.
> Raise tank pressure or cut line losses.`

### 1.4 `NOT_MODELLED` — modül düzeyi sabit

Modül, **bilinçli olarak modellemediklerini** modül düzeyinde bir sözlükte
toplar ve bu sözlük çıktıya aynen konur.

```bash
grep -rn "NOT_MODELLED\s*=" hrma/ --include='*.py' | grep -v __pycache__
```

Ölçüldü — 10 modül kendi `NOT_MODELLED` sabitini tanımlıyor:
`launch_site`, `valve_feedline`, `gimbal_mount`, `two_phase_loss`,
`turbopump_sizing`, `acoustic_modes`, `igniter_sizing`,
`fea/bridge` (`BRIDGE_STATUS_NOT_MODELLED`), `flow/separation`,
`flow/quasi1d`. Anahtar toplamı: `NOT_MODELLED` deponun Python
kaynağında **209 satırda** geçiyor.

Ölçülmüş örnek — `igniter_sizing.NOT_MODELLED` 9 başlık taşıyor:
`ignition_chemistry`, `flame_spreading`, `hard_start_dynamics`, `hypergolic`,
`electrical`, `torch_internals`, `igniter_hardware`, `propellant_properties`,
`restart`.

**Beyanın taahhüdü — üç madde:**

1. Her madde **niçin** modellenmediğini ve **bunun yerine ne verildiğini**
   yazar. `turbopump_sizing.NOT_MODELLED['cavitation_dynamics']`:
   *"…The NPSH margin reported here is a steady design-rule comparison of
   available vs required NPSH, not a cavitation stability statement."*
   Yani beyan yalnız eksiği değil, **verilen sayının hükmünü** de daraltır.
2. Beyan **çıktıya konur** — kullanıcıya ulaşmayan beyan yoktur.
3. Bir kalem gerçekten modellenince beyan **kaldırılır.** Bu, bekçi
   testlerini de ilgilendirir: "beyan sayısı ≥ N" biçiminde yazılan bir
   bekçi, bağlama yapıldığında sayı düşeceği için **doğru davranışı kırar**.
   Bu depoda ölçülmüş bir kalıptır ("kusuru kilitleyen bekçi") ve bağlama
   dalgalarında testler yeni sözleşmeye güncellenir.

### 1.5 Örnek: `thermal_protection` — üç kipli modül

`hrma/analysis/thermal_protection.py`, sözleşmenin en olgun örneğidir.

* Sınıf `ThermalProtectionAnalyzer` üç kip sunar: `ablative_thickness`
  (Q\* ablasyon modeli), `heat_sink_transient` (1B geçici iletim, explicit
  sonlu fark, CFL-güvenli `dt`), `radiation_equilibrium` (ışıma dengesi,
  bisection). Tek bir dağıtıcı vardır: `analyze(mode, **kwargs)`.
* Malzeme verisi politikası açıkça yazılıdır: merkezî veritabanında bulunan
  her şey `hrma.data.materials_db.get_material()` üzerinden okunur — **tek
  doğruluk kaynağı.** Q\* ablasyon sabitleri ve C-103 / karbon-karbon uzantı
  limitleri merkezî DB'de bulunmayan, modele özgü **literatür bandı**
  verileridir ve modülde kaynak atfı + "literature band" notuyla tutulur.
  Band verildiğinde varsayılan olarak **konservatif uç** seçilir (düşük Q\* =
  daha hızlı gerileme = daha kalın astar).
* Bartz taşınım katsayısı `h_g` bu modüle **girdidir**, burada hesaplanmaz;
  onu `heat_transfer_analysis` üretir. Modüller birbirinin işini tekrar
  yapmaz.
* Modül, künye hatasını bile kayda geçirir: metin boyunca "SP-8091" yazılıydı,
  ölçüldü ki SP-8091 *The Planet Saturn* monografıdır; doğrusu iç yalıtım için
  SP-8093, ablatif lüle astarı için SP-8115'tir. Düzeltme dosyanın içinde
  gerekçesiyle durur.
* Modül **kendi borcunu da kaydeder**: Stefan-Boltzmann sabiti burada yeniden
  tanımlıdır, çünkü depoda tek bir fizik-sabitleri modülü yoktur; not
  "MERKEZİLEŞTİRME BORCU" başlığıyla yazılıdır →
  [teknik-borc.md](teknik-borc.md) § 2.

---

## 2. Motor ↔ analiz sınırı

### 2.1 Yön

```
motor  ──(SI sayılar)──▶  analiz modülü
motor  ◀──(beyanlı dict)──  analiz modülü
```

Analiz modülü motoru **tanımaz**. Motor sınıfı:

1. kendi durumundan (`self.P_c`, `self.throat_diameter`, malzeme anahtarı…)
   modülün istediği SI argümanlarını çıkarır,
2. modülü çağırır,
3. dönen sözlüğü **kendi sonuç sözlüğüne bir blok olarak** yerleştirir.

Ölçülmüş yerleştirme deseni (hibrit):

```
basic_results['closure_joint']       = self._closure_joint_block()
basic_results['feed_water_hammer']   = self._feed_water_hammer_block()
basic_results['acoustic_modes']      = self._acoustic_modes_block(basic_results)
basic_results['nozzle_flow_quasi1d'] = self._nozzle_flow_block(basic_results)
basic_results['igniter_sizing']      = self._igniter_sizing_block(basic_results)
```

Blok üretici metotlar (`_*_block`) sözleşmenin motor tarafındaki yüzüdür:
birim dönüşümünü, alan adlarını ve "girdi yoksa ne olur" kararını **onlar**
verir.

### 2.2 Girdi yoksa ne olur

Değişmez kural: **girdi yoksa uydurulmaz, `NOT_MODELLED` beyanı konur.**
Bir blok üretici, gerekli girdiyi bulamazsa varsayılan bir sayı seçip
hesaplamaz; bloğu beyanla doldurur. Bu, bağlama dalgalarının yazılı
kuralıdır ve "sahte veri yasağı"nın kod karşılığıdır.

### 2.3 Koşullu bağlama

Bir modül, motor tipine göre **anlamlı olmadığı yerde bağlanmaz** ve bu da
beyan edilir. Ölçülmüş örnekler:

| Kural | Gerekçe |
|---|---|
| C1 turbopompa yalnız turbopompalı çevrimde (`gas_generator` / `staged` / `expander`) | Basınç beslemeli motorda pompa yoktur; blok "yok" diye beyanla geçer |
| A5 pasif termal koruma yalnız ablatif/radyatif soğutmada | Rejeneratif soğutmada `regen_cooling` zaten var; ikisini birden uygulamak çift sayımdır |
| İki-faz kaybı Isp'ye uygulanırken çift sayım denetimi | Mevcut Isp zaten bir verim çarpanı taşıyorsa ikinci kez düşürülmemeli |

---

## 3. `hrma/fea/bridge.py` — sözleşmenin referans belgesi

FEA çözücüleri (`structural_axisym`, `thermal_axisym`, `mesh_axisym`) saf
geometri + malzeme + yük alır ve **motor sözlüğüne hiç bağımlı değildir.**
Motor sözlüğünün alan adlarını, birimlerini ve beyan zincirini bilen **tek**
katman `bridge.py`'dir.

Köprünün alan haritası kod okunarak çıkarılmıştır ve hangi motorda hangi
alanın okunduğu tek tek yazılıdır:

| Girdi | Kaynak |
|---|---|
| Kontur | `results['nozzle_contour']['points']` — `[[z_m, r_m], …]`, **metre**. Origin sözleşmesi: ilk nokta konverjan girişi (z = 0, r = kamara yarıçapı). Blok yoksa **kontur uydurulmaz → red** |
| Cidar kalınlığı | Hibrit `structural_analysis.chamber_analysis.wall_thickness_used_mm`; sıvı `structural_analysis.chamber_structure.wall_thickness`; katı `structural_analysis.case_analysis.wall_thickness_mm`. Alan yoksa **varsayılan kalınlık uydurulmaz → red** |
| Malzeme | Motorun kendi yayımladığı malzeme anahtarı → `materials_db`. `E`, `ν` yalnız `materials_db`'dedir (motor çözücülerinin hiçbiri E/ν kullanmaz). Kayıt yoksa → red |
| Akma dayanımı | **Motorun kendi yayımladığı değer önceliklidir** — köprünün emniyet katsayısı, motorun kullandığı dayanımdan sapmamalıdır. Yayım yoksa DB değeri kullanılır ve hangisinin kullanıldığı `_basis`te yazılır |
| İç basınç | `results['chamber_pressure']` [bar] → Pa |

Ve bilinen sınır aynı yerde beyanlıdır: hiçbir motor sonucu lüle boyunca
P(x) yayımlamadığı için iç yüzeye **sabit** Pc uygulanır.

**Bu desen genelleştirilebilir kuraldır:** yeni bir çözücü eklenirken çözücü
saf tutulur, motor sözlüğünü bilen ince bir köprü katmanı yazılır. Köprü
katmanı, alan adı değiştiğinde kırılacak **tek** yerdir.

---

## 4. Uç katmanı ↔ motor sözleşmesi

### 4.1 Motor `dict` döndürmek zorundadır

```python
class EngineContractViolation(TypeError):   # app.py:3119
def _require_dict_result(results, engine_name, route_name):   # app.py:3132
```

Motor sözlük dışı bir şey döndürürse istisna yükselir ve uç **HTTP 500**
verir. Bu kapıdan önceki davranış ölçülmüştü: `None.setdefault` çağrısı geniş
bir `try/except` tarafından yutuluyor, log `success` yazıyor ve istemciye
**HTTP 200 + `null`** gidiyordu. "Sessiz 200" bu depoda adı konmuş bir kusur
sınıfıdır.

Buna bağlı ikinci kural: **`try/except` blokları dar tutulur.** Çizim
üretimini saran koruma yalnız çizimi sarar; motor sonucunun bozukluğunu
yutmaz. Geometri dönüşümü bilinçli olarak `try` **dışına** alınmıştır.

### 4.2 Hata da sözleşmedir

Motor, hesabı yapamadığında istisna fırlatmak yerine **hata sözlüğü**
döndürebilir:

```python
{'error': 'Invalid grain geometry',
 'error_i18n': _w('warn.solid.invalid_grain_geometry', 'critical')}
```

Bu biçimi tanıyan çağıranlar ölçüldü: `run_monte_carlo`, `uq_adapters` ve
`solid.html` — üçü de `error` anahtarını denetler. Yeni bir çağıran eklenirken
bu sözleşme korunur.

### 4.3 Uç katmanı sayı uydurmaz

Uç katmanı, motorun girdisini **tamamlamaz**. Ölçülmüş kural
(`_build_solid_engine`, `app.py:3140`): alan gelmediyse motora hiç geçilmez,
değer seçilen yakıtın merkezî katalog kaydından çözülür ve kaynağı
(`request` / `central_catalog:<yakıt>` / `engine_constructor_default:…`)
yanıtta beyan edilir.

Buna bağlı olarak uç katmanı **kazanılmamış onay** da vermez:
`_withhold_unearned_vessel_verdict` (`app.py:6578`), kullanıcı kasa kalınlığı
girmediyse "basınçlı kap PASS" hükmünü geri çeker — cidarı HRMA'nın kendisi
emniyet katsayısını sağlayacak şekilde boyutlayıp sonra aynı cidarı sınamak
totolojidir.

### 4.4 Dil sözleşmesi

Arka uç **metin üretmez, kod üretir**. Uyarı nesnesi:

```json
{"code": "warn.solid.burn_rate_off_catalog",
 "params": {"propellant": "apcp", "user_rate_mmps": 18.18,
            "catalog_rate_mmps": 8.12, "ratio": 2.24},
 "severity": "warning"}
```

Metin istemcide (`i18n_*.js`) çözülür. Bunun sözleşme olmasının sebebi
ölçülebilirlik: bir i18n kapsam bekçisi, arka ucun ürettiği her kodun
sözlükte EN + TR karşılığı olduğunu sınayabilir; serbest metin sınanamaz.

---

## 5. Veri katmanı sözleşmesi

| Kural | Yeri |
|---|---|
| Malzeme mekanik + termal özellikleri **tek** kayıttan okunur | `data/materials_db.get_material` / `get_material_safe` |
| Saint-Robert `a`, `n` katsayıları **tek** katalogdan çözülür | `data/burn_rate_db` + `/api/burn-rate/resolve` |
| Aynı sayı iki dosyada tanımlıysa merkezî dosyadan import edilir | `hrma/constants.py` (CLAUDE.md kural 11) |
| Deney kayıtları git izlemeli JSON'dur; `inputs` ve `measured` **ayrı** alanlardadır | `data/validation_records/`, `SCHEMA.md` |

Son maddenin gerekçesi döngüsellik korumasıdır: ölçümün girdiye sızması
korelasyonu anlamsız kılar; şema ayrımı bunu yapısal olarak engeller ve
"aşırı iyileşme" uyarısı kaçakları yakalamak için tasarlanmıştır.

Sabitler için sözleşmenin **kısmen çiğnendiği** bilinen bir yer vardır
(Stefan-Boltzmann, 6 ayrı tanım) → [teknik-borc.md](teknik-borc.md) § 2.

---

## 6. Beyan → kapı zinciri (en önemli kural)

Bir beyan yazmak yetmez; **onu okuyan bir kapı** olmak zorundadır. Depoda
çalışan örnekler:

| Beyan | Onu okuyan kapı | Sonuç |
|---|---|---|
| `convergence_achieved`, `termination_reason`, `pressure_solver_failed_steps` | `SolidRocketEngine.calculate_performance` yakınsama kapısı | Yakınsamamış ve anormal biten koşuda **sonuç üretilmez**; sınırda üretilir ama `design_summary.status` düşürülür |
| Kullanıcı kasa kalınlığı verdi mi | `_withhold_unearned_vessel_verdict` | `vessel_status` PASS diyemez |
| Kontur / cidar / malzeme alanları var mı | `fea/bridge.py` | `NOT_MODELLED` ile red, mesh üretilmez |
| Motor sonucu sözlük mü | `_require_dict_result` | HTTP 500 |
| Girdi eksiksiz mi | `calculate_solid` eksiksizlik kapısı | HTTP 422 |
| Yanma hızı kataloğa uyuyor mu | `_check_burn_rate_coefficients` | `warn.solid.burn_rate_off_catalog` |

**Bekçi testi kuralı:** her kapı, *kasıtlı olarak bozulmuş* bir girdiyle
sınanır ve kırmızıya düşmesi gerekir. 4 Ağustos denetçi turunda 6 bekçi
kasıtlı kusurla sınandı, 6/6 kırmızıya düştü — yani bekçiler totoloji
değildi. Yeni bir kapı eklenirken bu sınav tekrarlanır.

---

## 7. Yeni modül eklerken kontrol listesi

Kulvarı ne olursa olsun, `hrma/analysis/` altına giren her modül:

- [ ] Anahtar kelimeli, **SI birimli, birimi adında yazılı** argümanlar alır.
- [ ] Motor sözlüğü, `request`, dosya sistemi ya da ağ **görmez**.
- [ ] Dönüş `dict`, içinde **`_basis`** var; sayının kaynağı gerekiyorsa
      `_source`, hükmü gerekiyorsa `_status`.
- [ ] Modül düzeyinde **`NOT_MODELLED`** sözlüğü tanımlar; her madde niçin
      modellenmediğini **ve** verilen sayının hükmünü daraltır.
- [ ] Fiziksel olarak imkânsız girdide **`ValueError` + ne yapılacağını
      söyleyen mesaj** üretir; sessizce sayı döndürmez.
- [ ] Malzeme/itici verisi merkezî DB'den gelir; modele özgü literatür bandı
      ise künyeli ve "band" etiketiyle tutulur, **konservatif uç varsayılan**.
- [ ] **Doğrulama kümesiyle** gelir: analitik çözüm, yayımlanmış motor verisi
      ya da korunum kontrolü. Doğrulaması olmayan modül yayımlanmaz.
- [ ] Motora bağlanırken **blok üretici** (`_*_block`) yazılır; girdi yoksa
      `NOT_MODELLED` beyanı konur, sayı uydurulmaz.
- [ ] Beyanı **okuyan bir kapı** vardır; kapı kasıtlı kusurla sınanmıştır.
- [ ] Kullanıcıya görünen her metin **i18n kodu** olarak üretilir.

Bu listenin son üç maddesi, bu depoda kusurun en çok çıktığı yerlerdir:
"yazıldı ama bağlanmadı", "beyan edildi ama okunmadı", "arka uç doğru ama
şablon göndermiyor".
