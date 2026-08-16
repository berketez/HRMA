# HRMA — biçimsel olarak doğrulanmış varsayımlar

**Tarih:** 2 Ağustos 2026 · **Lean:** 4.32.2 · **Mathlib:** v4.32.2 (pinli)
**Denetlenen depo:** `/Users/apple/HRMA`, commit `48f2f37`

> **Not (14 Ağustos 2026):** Bu dosya, ispatların yazıldığı güne ait **tarihî
> anlık görüntüdür**; içindeki Python satır numaraları `48f2f37` commit'ine
> göredir ve o günden beri kaymıştır. **Güncel ve makine-denetimli bağ**
> `formal/registry.json`'dadır; denetim `python3 formal/check.py` ile yapılır.
> Çalıştırma komutları için `formal/README.md`'ye bak (proje artık
> `~/Desktop/dosyalar/lean-lab`'dan bu depoya taşındı).

Bu dosya, HRMA'nın koduna gömülü **sözlü varsayımların** hangilerinin makine
düzeyinde ispatlandığını gösterir. Her teorem genel matematik değil, koddaki
belirli bir satırın gerekçesidir.

## Neden

HRMA'nın hesap zincirinde çözücüye "bu fonksiyonun tek kökü var", "bu formül
kesin", "bu tablo sürekli" gibi varsayımlar veriliyor. Bunlar yorum satırında
yazılı ama hiçbir yerde **denetlenmiyor**. Yanlışlarsa çözücü sessizce yanlış
dala oturur — test yeşil kalır, sayı yanlış çıkar.

Denetimlerimizde bu sınıftan üç somut hata bulundu ve düzeltildi:
ISA tablosunun 100 km satırı elle `1000 K` yazılmıştı (doğrusu `186,946 K`);
lüle kütlesi ince kabukla hesaplanıyordu (aynı parçaya 2,5 kat farklı iki
kütle); enjektör buhar basıncını yanlış akışkandan alıyordu. Aşağıdaki
teoremler bu üç sınıfın **tekrar oluşamayacağını** gösteriyor.

## Doğrulanma durumu

Her teoremin altında `#print axioms` çalıştırıldı. Çıktının hepsi
`[propext, Classical.choice, Quot.sound]` — yani **hiçbirinde `sorryAx` yok**,
ispatlarda delik bırakılmadı.

```bash
cd ~/Desktop/dosyalar/lean-lab && lake build
```

## Teoremler

### 1. Alan–Mach bağıntısının tek kökü — `LeanLab/HRMA.lean`

Koruduğu satır: `hrma/analysis/transient_ballistics.py:314-319`

```python
Me = brentq(area_ratio, 1.0001, 50.0)
```

`brentq` aralıkta **tek kök** varsayar. Varsayım geçerli değilse çözücü
sessizce yanlış dala oturur.

| Teorem | Ne diyor |
|---|---|
| `areaRatio_strictMonoOn` | Alan oranı `γ > 1` için `[1, ∞)` üzerinde kesin monoton artandır |
| `areaRatio_root_unique` | Dolayısıyla o aralıkta iki kök varsa eşittirler |

### 2. `brentq` alt sınırının gerekçesi — `LeanLab/HRMANozzleBranch.lean`

Aynı satır, ama bu sefer **neden `1` değil `1.0001`** sorusu.

| Teorem | Ne diyor |
|---|---|
| `areaRatio_strictAntiOn` | Aynı fonksiyon `(0, 1]` üzerinde kesin monoton **azalan**dır |
| `areaRatio_subsonic_root_unique` | Subsonik kök de tektir |
| `branches_disjoint` | Subsonik kök ile süpersonik kök asla aynı sayı değildir |
| `bracket_excludes_subsonic` | `1 < a` seçilen `[a, b]` aralığı subsonik dalın hiçbir noktasını içermez |

Sonuç: `1.0001` sihirli sayı değil, ispatlanmış bir dal ayrımının sayısal
karşılığı. `M = 1` dönüm noktası olduğu için tipik `ε > 1`'de denklemin **iki**
kökü vardır; diverjan lülede fiziksel olan süpersonik olandır.

### 3. Kesik koni halkasının hacmi — `LeanLab/HRMAGeometry.lean`

Koruduğu satır: `hrma/engines/nozzle_design.py:838-843`

```python
#   V = π·(2·t·r_ort + t²)·L
vol_div = np.pi * (2.0 * t_w * (rt + re) / 2.0 + t_w ** 2) * L_div
```

| Teorem | Ne diyor |
|---|---|
| `frustumAnnulusVolume_eq_integral` | Kapalı biçim, disk integraliyle **birebir** aynı — yaklaşım değil, kesin |
| `frustum_minus_thinShell` | İnce kabuk yaklaşımının hatası **tam olarak** `π·t²·L` |
| `thinShell_lt_frustum` | Hata tek yönlü: ince kabuk her zaman **eksik** tahmin eder |
| `thinShell_relative_error` | Bağıl hata `t²/(2·t·r_ort + t²)` — cidar/yarıçap oranıyla büyür |

`t²` terimi "ikinci mertebeden, ihmal edilebilir" görünür. Ölçülen 2,5 katlık
kütle farkı bunun neden yanlış olduğunu gösteriyor; son teorem bunun kapalı
biçimi.

### 4. ISA katman tablosunun tutarlılığı — `LeanLab/HRMAAtmosphere.lean`

Koruduğu satır: `hrma/constants.py:49-62`, `isa_temperature`

Parçalı tanımlı fonksiyonda her katmanın taban sıcaklığı, bir öncekinin o
irtifadaki değerine eşit olmak zorundadır. Değilse fonksiyon sınırda sıçrar ve
aynı irtifayı 10999 m / 11001 m diye sorduğunda farklı atmosfer alırsın.

| Teorem | Ne diyor |
|---|---|
| `isaLayers_all_continuous` | Altı katman sınırının **hepsi** sürekli (0/11/20/32/47/51/71 km) |
| `isaTopTemperature` | Tablo tepesi (84,852 km) sıcaklığı `186,946 K` |
| `isaTop_not_1000` | Elle yazılan `1000 K` yanlıştı ve doğru değerin **5 katından fazlası** |
| `boundary_choice_irrelevant` | Sınırda hangi katmanın seçildiği sonucu değiştirmez |

Ses hızı `√T` ile ölçeklendiği için `1000 K` hatası o irtifadaki Mach ve
sürükleme hesabını kökten bozuyordu.

### 5. Kavitasyon uyarısının hata yönü — `LeanLab/HRMAInjector.lean`

Koruduğu satır: `hrma/utils/injector_design.py:903-905`

```python
k_c = (self.P_tank - self.p_vapor_bar) / max(self.P_tank - self.P_c, 1e-9)
if k_c < NURICK_KC_LIMIT:      # 1.5
```

`p_vapor_bar` her zaman kesin bilinmez. Kritik soru: yanlış tahmin edersek
hata hangi yöne düşer?

| Teorem | Ne diyor |
|---|---|
| `cavitationNumber_strictAnti` | `K_c`, `P_v`'nin kesin azalan fonksiyonudur |
| `underestimate_inflates_kc` | `P_v` küçük tahmin edilirse `K_c` büyük çıkar |
| `conservative_when_overestimated` | `P_v`'yi **büyük** alıp eşiği geçmek **güvenli** — gerçek `K_c` de eşiğin üstünde |
| `underestimate_can_miss_warning` | `P_v`'yi **küçük** alıp eşiği geçmek **hiçbir şey kanıtlamaz** (somut karşı örnek) |
| `kc_below_limit_iff` | Eşik ölçütünün kapalı biçimi: `K_c < 1,5 ⟺ P_v > P₁ − 1,5(P₁ − P₂)` |

Karşı örnek: `P₁ = 50 bar`, `P₂ = 20 bar`. Varsayılan `P_v = 4` → `K_c ≈ 1,53`
(uyarı yok); gerçek `P_v = 10` → `K_c ≈ 1,33` (uyarı gerekli). Program "risk
yok" der, gerçekte kavitasyon vardır.

**Mühendislik sonucu:** `p_vapor_bar` belirsizken "K_c ≥ 1,5, risk yok" çıktısı
**kazanılmamış bir hükümdür**. Hata güvensiz tarafa düşer.

## Toplam

| Dosya | Teorem |
|---|---:|
| `HRMA.lean` | 2 |
| `HRMANozzleBranch.lean` | 4 |
| `HRMAGeometry.lean` | 4 |
| `HRMAAtmosphere.lean` | 4 |
| `HRMAInjector.lean` | 5 |
| **Toplam** | **19** |

## Sınır — bu ispatlar neyi kanıtlamaz

Dürüst olmak gerekirse:

* İspatlar **Lean'de yeniden yazılmış** ifadeler üzerinedir. Python kodunun
  o ifadeyi doğru uyguladığı ayrıca sınanmalıdır (bunun için test paketi var).
  Lean ile Python arasında otomatik bağ yoktur; bağ, dosya başındaki alıntı ve
  satır numarasıdır ve **elle** korunur.
* Fiziksel modelin kendisi değil, modelin **matematiksel tutarlılığı**
  ispatlanır. "Nurick ölçütü doğru ölçüttür" bir deney sorusudur, ispat
  sorusu değil.
* Kayan nokta aritmetiği modellenmez; teoremler gerçel sayılarda geçerlidir.
  Yuvarlama davranışı ayrı bir konudur.

---

# Ek — 16 Ağustos 2026: CFD analitik referans kulvarı

**Lean:** 4.32.2 · **Mathlib:** v4.32.2 (pinli) ·
**Dosya:** `LeanLab/HRMACfdReferans.lean` (20 kayıtlı teorem)

v3 CFD doğrulama merdiveninin (`docs/mimari/cfd-tasarimi.md` §"Lean biçimsel
ayak", Berke talimatı 15 Ağu) analitik referans formülleri kilitlendi. Sayısal
çözücünün kendisi İSPATLANMADI — o, testle doğrulanır (ayrıklaştırma bir
yaklaşımdır, teorem konusu değildir). İspatlanan şey, TESTLERİN karşılaştırdığı
kapalı-form bağıntıların türetim tutarlılığıdır: referans formül yanlış
yazılmışsa test o yanlışa karşı doğrular — yeşil kalır, sayı yanlış olur.
Bu kulvar o sınıfı kapatır.

## 6. İzantropik durma/statik bağıntıları

Koruduğu satırlar: `hrma/flow/quasi1d.py:163-165, 203, 234`
(`isentropic_ratios`, `mach_from_area_ratio` erken dönüşü,
`mach_from_pressure_ratio`); test: `tests/cfd/test_izantropik_lule.py`.

| Teorem | Ne diyor |
|---|---|
| `isentropic_state_identity` | `P/P0 = (T/T0)·(ρ/ρ0)` — üç oran hâl denklemiyle cebirsel tutarlı; üslerden biri yanlış olsa sağlanmazdı |
| `isentropic_process_identity` | `P/P0 = (ρ/ρ0)^γ` — `p ∝ ρ^γ` yasası iki üslü ifadenin cebirsel sonucu |
| `pRatio_strictAntiOn` | `P/P0`, `M ≥ 0` üzerinde kesin azalan — kapalı-biçim terslemenin tekliği |
| `machFromPressureRatio_recovers` | Terslenmiş formül `M`'yi TAM geri verir — yaklaşıklık değil özdeşlik |
| `areaRatio_at_sonic` | `M = 1`'de `A/A* = 1` — `return 1.0` erken dönüşünün gerekçesi |

## 7. Normal şok (Rankine-Hugoniot) sıçrama bağıntıları

Koruduğu satırlar: `hrma/flow/quasi1d.py:256-261`
(`normal_shock_relations`) ve bağımsız kopyası
`tests/cfd/test_normal_sok.py:87-91` (`_normal_sok`).

| Teorem | Ne diyor |
|---|---|
| `shockM2sq_pos` | `M₂² > 0` — `np.sqrt`'e negatif argüman gidemez |
| `shockM2sq_lt_one` | `M₂² < 1` — şok ardı HER ZAMAN ses-altı |
| `shockM2_subsonic` | `M₂ = √(M₂²) < 1` — testin ses-altı A2* dalının ön şartı |
| `shockPRatio_gt_one` | `P₂/P₁ > 1` — genleşme şoku formülden çıkamaz |
| `shockRhoRatio_gt_one` | `ρ₂/ρ₁ > 1` — yoğunluk şokta artar |
| `shockTRatio_eq_p_div_rho` | `T₂/T₁ = (P₂/P₁)/(ρ₂/ρ₁)` — üç formül hâl denklemiyle tutarlı |
| `normalShock_satisfies_conservation` | **Türetim:** sıçrama formülleri kütle+momentum+enerji korunumunun ÜÇÜNÜ birden sağlar — formüller rastgele değil, korunum sisteminin kapalı çözümü |
| `shockStagLoss_forms_agree` | Testin `P₀₂/P₀₁` biçimi ile quasi1d'nin Anderson Eş. 3.63 biçimi cebirsel ÖZDEŞ — iki bağımsız gerçekleme tanım gereği aynı sayıyı üretir |

## 8. HLLC ara-durum özdeşlikleri (Toro §10.4)

Koruduğu satırlar: `hrma/cfd/riemann.py:93` (`s_star`, Toro Eş. 10.37)
ve `113-119` (star bölge durumları, Toro Eş. 10.39).

| Teorem | Ne diyor |
|---|---|
| `hllcSStar_denom_neg` | Dalga sıralaması altında `dl < 0 < dr` → payda `< 0`: bölme dejenere olamaz |
| `hllcSStar_pressure_match` | Kodun `S*` formülü `p*_L = p*_R` eşitliğini (Eş. 10.36) cebirsel sağlar |
| `hllcSStar_unique` | `S*` bu eşitliğin TEK çözümü — varyant formül sessizce farklı fizik veremez |
| `hllcStar_mass_rh` | `coef` tanımı kütle RH koşulunu sağlar |
| `hllcStar_momentum_rh` | `coef·s_star` momentum RH koşulunu `p*` ile tam sağlar |
| `hllcStar_energy_rh` | `u_star_e` ifadesi enerji RH koşulunun çözümü — iç çarpan işareti yanlış olsa bozulurdu |

## 9. Boğulmuş debi (Anderson Eş. 5.23)

Koruduğu satır: `hrma/flow/quasi1d.py:275-277` (`choked_mass_flow`);
test: `tests/cfd/test_izantropik_lule.py:78-80` (bağımsız kurulum).

| Teorem | Ne diyor |
|---|---|
| `chokedMassFlow_derivation` | **Türetim:** kapalı biçim tam olarak `ρ*·a*·A*` çarpımı — üsteki `(γ+1)/(2(γ−1))`, `1/(γ−1)+1/2` birleşiminden; elle sadeleştirme hatası yok |

## Bilinçli daraltmalar (bu kulvarda İSPATLANMAYANLAR)

* **Entropi eşitsizliği** (`P₀₂/P₀₁ < 1`): logaritmalı gerçek bir analiz
  argümanı gerektirir (Anderson §3.6'nın kalkülüs kısmı); cebirsel kulvarın
  dışında bırakıldı. Kilitlenen, iki biçimin ÖZDEŞLİĞİ ve sıçramaların yönü.
* **Alan-Mach süpersonik/subsonik dal monotonlukları** zaten 1-2. bölümlerde
  (2 Ağustos) ispatlıydı; tekrarlanmadı, `areaRatio_at_sonic` mevcut
  `areaRatio` tanımının üstüne kuruldu.
* **Sayısal çözücü** (HLLC akı seçim mantığı, MUSCL, RK2, ayrıklaştırma):
  ispat konusu değil — test merdiveni doğrular (`tests/cfd/`).

## Güncel toplam (16 Ağustos 2026)

| Dosya | Kayıtlı teorem |
|---|---:|
| `HRMA.lean` | 2 |
| `HRMANozzleBranch.lean` | 4 |
| `HRMAGeometry.lean` | 4 |
| `HRMAAtmosphere.lean` | 4 |
| `HRMAInjector.lean` | 5 |
| `HRMACfdReferans.lean` | 20 |
| **Toplam** | **39** |
