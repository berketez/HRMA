import LeanLab.HRMA

/-!
# HRMA — CFD analitik referans bağıntılarının türetim kilitleri

v3 CFD doğrulama merdiveni (`docs/mimari/cfd-tasarimi.md` §"Lean biçimsel
ayak") sayısal çözücüyü İSPATLAMAZ; çözücü testle doğrulanır. Burada
kilitlenen şey, TESTLERİN karşılaştırdığı **analitik referans formüllerin**
matematiksel tutarlılığıdır. Bir referans formül yanlış yazılmışsa test o
yanlışa karşı doğrular — yeşil kalır, sayı yanlış olur. Aşağıdaki teoremler
o sınıfı kapatır.

Dört kulvar:

1. **İzantropik bağıntılar** — `hrma/flow/quasi1d.py:isentropic_ratios`,
   `area_ratio_from_mach`, `mach_from_pressure_ratio`;
   test: `tests/cfd/test_izantropik_lule.py`.
   Kaynak: Anderson, "Modern Compressible Flow", 3. baskı, Eş. 3.28-3.31, 5.20.
2. **Normal şok (Rankine-Hugoniot)** — `hrma/flow/quasi1d.py:
   normal_shock_relations`; test: `tests/cfd/test_normal_sok.py:_normal_sok`.
   Kaynak: Anderson Eş. 3.51/3.57/3.59/3.63; NACA Report 1135 Eş. 93-99.
3. **HLLC ara-durum özdeşlikleri** — `hrma/cfd/riemann.py:hllc_flux`.
   Kaynak: Toro, "Riemann Solvers and Numerical Methods for Fluid
   Dynamics", 3. baskı, §10.4 (Eş. 10.36, 10.37, 10.39).
4. **Boğulmuş debi** — `hrma/flow/quasi1d.py:choked_mass_flow`;
   test: `tests/cfd/test_izantropik_lule.py:test_bogaz_kutle_debisi_analitik`.
   Kaynak: Anderson Eş. 5.23; Sutton & Biblarz, 9. baskı, Eş. 3-24.

Bütün teoremler gerçel sayılar (ℝ) üzerindedir; kayan nokta ayrı konudur
(`formal/README.md` "Neyi KANITLAMIYOR").
-/

namespace HRMA

open Real Set

/-! ## 1. İzantropik durma/statik oranları

`hrma/flow/quasi1d.py:163-165`:

```python
t_ratio = 1.0 / (1.0 + 0.5 * (g - 1.0) * M * M)
p_ratio = t_ratio ** (g / (g - 1.0))
rho_ratio = t_ratio ** (1.0 / (g - 1.0))
```
-/

/-- Durma/statik sıcaklık oranı `T0/T = 1 + (γ−1)/2·M²` (Anderson Eş. 3.28). -/
noncomputable def stagTempRatio (γ M : ℝ) : ℝ := 1 + (γ - 1) / 2 * M ^ 2

/-- `T/T0` — kodun `t_ratio` değişkeni. -/
noncomputable def tRatio (γ M : ℝ) : ℝ := (stagTempRatio γ M)⁻¹

/-- `P/P0 = (T/T0)^(γ/(γ−1))` — kodun `p_ratio` değişkeni (Anderson Eş. 3.30). -/
noncomputable def pRatio (γ M : ℝ) : ℝ := tRatio γ M ^ (γ / (γ - 1))

/-- `ρ/ρ0 = (T/T0)^(1/(γ−1))` — kodun `rho_ratio` değişkeni (Anderson Eş. 3.31). -/
noncomputable def rhoRatio (γ M : ℝ) : ℝ := tRatio γ M ^ (1 / (γ - 1))

/-- `T0/T` her gerçek `M` için pozitiftir (γ > 1). -/
lemma stagTempRatio_pos {γ : ℝ} (hγ : 1 < γ) (M : ℝ) :
    0 < stagTempRatio γ M := by
  unfold stagTempRatio
  nlinarith [sq_nonneg M]

/-- `T/T0` pozitiftir. -/
lemma tRatio_pos {γ : ℝ} (hγ : 1 < γ) (M : ℝ) : 0 < tRatio γ M :=
  inv_pos.mpr (stagTempRatio_pos hγ M)

/--
**İdeal gaz hâl özdeşliği.** Üç oran bağımsız değildir: `P/P0 = (T/T0)·(ρ/ρ0)`
(hâl denklemi `p = ρRT` durma durumuna bölününce). Kodun üç ayrı satırda
kurduğu üçlü, bu özdeşliği CEBİRSEL olarak sağlar — üs seçimlerinden biri
yanlış yazılsaydı sağlamazdı.
-/
theorem isentropic_state_identity {γ : ℝ} (hγ : 1 < γ) (M : ℝ) :
    pRatio γ M = tRatio γ M * rhoRatio γ M := by
  have ht : 0 < tRatio γ M := tRatio_pos hγ M
  have hγ1 : γ - 1 ≠ 0 := sub_ne_zero.mpr (ne_of_gt hγ)
  have he : γ / (γ - 1) = 1 + 1 / (γ - 1) := by
    field_simp
    ring
  unfold pRatio rhoRatio
  rw [he, Real.rpow_add ht, Real.rpow_one]

/--
**İzantropik süreç özdeşliği.** `P/P0 = (ρ/ρ0)^γ` — yani `p ∝ ρ^γ` yasası,
kodun `t_ratio` üzerinden kurduğu iki üslü ifadenin cebirsel sonucudur
(Anderson Eş. 3.29-3.31 zinciri).
-/
theorem isentropic_process_identity {γ : ℝ} (hγ : 1 < γ) (M : ℝ) :
    pRatio γ M = rhoRatio γ M ^ γ := by
  have ht : (0:ℝ) ≤ tRatio γ M := (tRatio_pos hγ M).le
  have hγ1 : γ - 1 ≠ 0 := sub_ne_zero.mpr (ne_of_gt hγ)
  unfold pRatio rhoRatio
  rw [← Real.rpow_mul ht]
  congr 1
  field_simp

/--
**Monotonluk (dar biçim).** `P/P0`, `M ≥ 0` üzerinde kesin azalandır.
`mach_from_pressure_ratio`'nun kapalı-biçim terslemesinin TEK değer
döndürmesinin gerekçesi: azalan fonksiyonun tersi tektir.
-/
theorem pRatio_strictAntiOn {γ : ℝ} (hγ : 1 < γ) :
    StrictAntiOn (pRatio γ) (Set.Ici (0:ℝ)) := by
  intro a ha b hb hab
  have ha0 : (0:ℝ) ≤ a := ha
  have hb0 : (0:ℝ) < b := lt_of_le_of_lt ha0 hab
  have hsa : 0 < stagTempRatio γ a := stagTempRatio_pos hγ a
  have hsb : 0 < stagTempRatio γ b := stagTempRatio_pos hγ b
  have hsq : a ^ 2 < b ^ 2 := by nlinarith
  have hstag : stagTempRatio γ a < stagTempRatio γ b := by
    unfold stagTempRatio
    have hcoef : (0:ℝ) < (γ - 1) / 2 := by linarith
    nlinarith
  have ht : tRatio γ b < tRatio γ a := by
    unfold tRatio
    rw [inv_eq_one_div, inv_eq_one_div]
    exact div_lt_div_of_pos_left one_pos hsa hstag
  have htb : (0:ℝ) ≤ tRatio γ b := (tRatio_pos hγ b).le
  unfold pRatio
  exact Real.rpow_lt_rpow htb ht (div_pos (by linarith) (by linarith))

/--
**Basınç-oranı terslemesi kapalı biçimi geri getirir.**
`hrma/flow/quasi1d.py:234` şunu hesaplar:
`M = √( 2/(γ−1) · [(P0/P)^((γ−1)/γ) − 1] )`.
Bu teorem, `P0/P = (pRatio)⁻¹` girildiğinde formülün TAM OLARAK `M`'yi geri
verdiğini gösterir: tersleme yaklaşıklık değil özdeşliktir (M ≥ 0 dalında).
-/
theorem machFromPressureRatio_recovers {γ : ℝ} (hγ : 1 < γ) {M : ℝ}
    (hM : 0 ≤ M) :
    Real.sqrt (2 / (γ - 1) * ((pRatio γ M)⁻¹ ^ ((γ - 1) / γ) - 1)) = M := by
  have hγ0 : (0:ℝ) < γ := by linarith
  have hγ1 : (0:ℝ) < γ - 1 := by linarith
  have hs : 0 < stagTempRatio γ M := stagTempRatio_pos hγ M
  have h1 : (pRatio γ M)⁻¹ = stagTempRatio γ M ^ (γ / (γ - 1)) := by
    unfold pRatio tRatio
    rw [Real.inv_rpow hs.le, inv_inv]
  have h2 : (stagTempRatio γ M ^ (γ / (γ - 1))) ^ ((γ - 1) / γ)
      = stagTempRatio γ M := by
    rw [← Real.rpow_mul hs.le]
    rw [show γ / (γ - 1) * ((γ - 1) / γ) = 1 by
      field_simp]
    exact Real.rpow_one _
  rw [h1, h2]
  rw [show 2 / (γ - 1) * (stagTempRatio γ M - 1) = M ^ 2 by
    unfold stagTempRatio; field_simp; ring]
  exact Real.sqrt_sq hM

/--
**M = 1'de A = A\*.** Alan-Mach bağıntısı (`HRMA.areaRatio`, Anderson Eş. 5.20)
sonik noktada tam 1 verir. `hrma/flow/quasi1d.py:mach_from_area_ratio`'nun
`A/A* ≤ 1+1e-12 → return 1.0` erken dönüşünün gerekçesi: sonik nokta
bağıntının değme noktasıdır (iki dalın kesişimi), yakınında kök aramak
yerine 1 döndürmek doğrudur.
-/
theorem areaRatio_at_sonic {γ : ℝ} (hγ : 1 < γ) : areaRatio γ 1 = 1 := by
  have hγp : γ + 1 ≠ 0 := ne_of_gt (by linarith)
  unfold areaRatio ratio
  rw [show 2 / (γ + 1) * (1 + (γ - 1) / 2 * (1:ℝ) ^ 2) = 1 by
    field_simp; ring]
  rw [Real.one_rpow, inv_one, one_mul]

/-! ## 2. Normal şok (Rankine-Hugoniot) sıçrama bağıntıları

`hrma/flow/quasi1d.py:256-261` (ve bağımsız kopya
`tests/cfd/test_normal_sok.py:_normal_sok`):

```python
m2sq = (1.0 + 0.5 * (g - 1.0) * m1sq) / (g * m1sq - 0.5 * (g - 1.0))
p2_p1 = 1.0 + 2.0 * g / (g + 1.0) * (m1sq - 1.0)
T2_T1 = p2_p1 * (2.0 + (g - 1.0) * m1sq) / ((g + 1.0) * m1sq)
p02_p01 = ...  # Anderson Eş. 3.63
```

Burada `m` değişkeni her yerde **M₁²** anlamındadır (kodun `m1sq`'i);
`M₁ > 1` hipotezi `m > 1` olarak taşınır.
-/

/-- Şok ardı Mach karesi `M₂²` (Anderson Eş. 3.51). `m = M₁²`. -/
noncomputable def shockM2sq (γ m : ℝ) : ℝ :=
  (1 + (γ - 1) / 2 * m) / (γ * m - (γ - 1) / 2)

/-- Statik basınç sıçraması `P₂/P₁` (Anderson Eş. 3.57). -/
noncomputable def shockPRatio (γ m : ℝ) : ℝ := 1 + 2 * γ / (γ + 1) * (m - 1)

/-- Yoğunluk sıçraması `ρ₂/ρ₁` (Anderson Eş. 3.53). -/
noncomputable def shockRhoRatio (γ m : ℝ) : ℝ := (γ + 1) * m / ((γ - 1) * m + 2)

/-- Sıcaklık sıçraması `T₂/T₁` — kodun satır 259'daki biçimi (Anderson Eş. 3.59). -/
noncomputable def shockTRatio (γ m : ℝ) : ℝ :=
  shockPRatio γ m * ((2 + (γ - 1) * m) / ((γ + 1) * m))

/-- `M₂²` paydası şok bölgesinde pozitiftir (γ > 1, m > 1). -/
lemma shockM2sq_denom_pos {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    0 < γ * m - (γ - 1) / 2 := by nlinarith

/-- `ρ₂/ρ₁` paydası pozitiftir. -/
lemma shockRhoRatio_denom_pos {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    0 < (γ - 1) * m + 2 := by nlinarith

/--
**`M₂²` pozitiftir** — koddaki `np.sqrt(m2sq)` çağrısına (satır 257) negatif
argüman gidemez; karekök her zaman tanımlıdır.
-/
theorem shockM2sq_pos {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    0 < shockM2sq γ m := by
  unfold shockM2sq
  exact div_pos (by nlinarith) (shockM2sq_denom_pos hγ hm)

/--
**Şok ardı ses-altıdır: `M₂² < 1`.** Süpersonik gelen akış (`M₁ > 1`) normal
şoktan HER ZAMAN ses-altı çıkar. `test_normal_sok`'un şok ardı dalı ses-altı
izantropik taşımasının (A2* dalı) ön şartı budur.
-/
theorem shockM2sq_lt_one {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    shockM2sq γ m < 1 := by
  unfold shockM2sq
  rw [div_lt_one (shockM2sq_denom_pos hγ hm)]
  nlinarith

/-- `M₂ = √(M₂²) < 1` — kodun döndürdüğü `mach2` değeri ses-altıdır. -/
theorem shockM2_subsonic {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    Real.sqrt (shockM2sq γ m) < 1 := by
  have h := Real.sqrt_lt_sqrt (shockM2sq_pos hγ hm).le (shockM2sq_lt_one hγ hm)
  simpa using h

/-- **Şok sıkıştırır: `P₂/P₁ > 1`.** Genleşme şoku formülden çıkamaz. -/
theorem shockPRatio_gt_one {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    1 < shockPRatio γ m := by
  unfold shockPRatio
  have h : 0 < 2 * γ / (γ + 1) * (m - 1) :=
    mul_pos (div_pos (by linarith) (by linarith)) (by linarith)
  linarith

/-- **Yoğunluk artar: `ρ₂/ρ₁ > 1`.** -/
theorem shockRhoRatio_gt_one {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    1 < shockRhoRatio γ m := by
  unfold shockRhoRatio
  rw [one_lt_div (shockRhoRatio_denom_pos hγ hm)]
  nlinarith

/--
**İdeal gaz sıçrama özdeşliği: `T₂/T₁ = (P₂/P₁)/(ρ₂/ρ₁)`.** Kodun satır
259'da `p2_p1·(2+(γ−1)m)/((γ+1)m)` olarak yazdığı çarpan tam olarak
`1/(ρ₂/ρ₁)`'dir; yani üç sıçrama formülü hâl denklemiyle tutarlıdır.
Formüllerden biri yanlış kopyalansaydı bu özdeşlik bozulurdu.
-/
theorem shockTRatio_eq_p_div_rho {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    shockTRatio γ m = shockPRatio γ m / shockRhoRatio γ m := by
  have hd : ((γ - 1) * m + 2) ≠ 0 := ne_of_gt (shockRhoRatio_denom_pos hγ hm)
  have hγp : γ + 1 ≠ 0 := ne_of_gt (by linarith)
  have hm0 : m ≠ 0 := ne_of_gt (by linarith)
  unfold shockTRatio shockRhoRatio
  field_simp
  ring

/--
**TÜRETİM TUTARLILIĞI: sıçrama formülleri korunum denklemlerini sağlar.**

Şok öncesi durum `(ρ₁, u₁, p₁)` ve `m = M₁² = ρ₁u₁²/(γp₁)` verilsin. Kodun
sıçrama formülleriyle kurulan şok ardı durum
`ρ₂ = ρ₁·(ρ₂/ρ₁)`, `u₂ = u₁/(ρ₂/ρ₁)`, `p₂ = p₁·(P₂/P₁)`
Rankine-Hugoniot korunum denklemlerinin ÜÇÜNÜ birden sağlar:

* kütle:    `ρ₂u₂ = ρ₁u₁`
* momentum: `ρ₂u₂² + p₂ = ρ₁u₁² + p₁`
* enerji:   `γ/(γ−1)·p₂/ρ₂ + u₂²/2 = γ/(γ−1)·p₁/ρ₁ + u₁²/2`

Yani `quasi1d.normal_shock_relations` (ve testin `_normal_sok`'u) rastgele
üç formül değil, korunum sisteminin kapalı çözümüdür. Formüllerden birine
yazım hatası girseydi bu teorem ispatlanamazdı.
-/
theorem normalShock_satisfies_conservation {γ ρ₁ u₁ p₁ m ρ₂ u₂ p₂ : ℝ}
    (hγ : 1 < γ) (hρ : 0 < ρ₁) (hp : 0 < p₁) (hm : 1 < m)
    (hMach : ρ₁ * u₁ ^ 2 = γ * p₁ * m)
    (hρ₂ : ρ₂ = ρ₁ * shockRhoRatio γ m)
    (hu₂ : u₂ = u₁ / shockRhoRatio γ m)
    (hp₂ : p₂ = p₁ * shockPRatio γ m) :
    ρ₂ * u₂ = ρ₁ * u₁ ∧
    ρ₂ * u₂ ^ 2 + p₂ = ρ₁ * u₁ ^ 2 + p₁ ∧
    γ / (γ - 1) * (p₂ / ρ₂) + u₂ ^ 2 / 2
      = γ / (γ - 1) * (p₁ / ρ₁) + u₁ ^ 2 / 2 := by
  have hγ1 : (0:ℝ) < γ - 1 := by linarith
  have hγp : (0:ℝ) < γ + 1 := by linarith
  have hm0 : (0:ℝ) < m := by linarith
  have hd : 0 < (γ - 1) * m + 2 := shockRhoRatio_denom_pos hγ hm
  have hr : 0 < shockRhoRatio γ m :=
    div_pos (by nlinarith) hd
  have hrne : shockRhoRatio γ m ≠ 0 := ne_of_gt hr
  have hρne : ρ₁ ≠ 0 := ne_of_gt hρ
  have hdne : ((γ - 1) * m + 2) ≠ 0 := ne_of_gt hd
  have hγpne : γ + 1 ≠ 0 := ne_of_gt hγp
  have hγ1ne : γ - 1 ≠ 0 := ne_of_gt hγ1
  have hmne : m ≠ 0 := ne_of_gt hm0
  have hu1sq : u₁ ^ 2 = γ * p₁ * m / ρ₁ := by
    rw [eq_div_iff hρne]
    linear_combination hMach
  subst hρ₂ hu₂ hp₂
  refine ⟨?_, ?_, ?_⟩
  · field_simp
  · rw [div_pow, hu1sq]
    unfold shockRhoRatio shockPRatio
    field_simp
    ring
  · rw [div_pow, hu1sq]
    unfold shockRhoRatio shockPRatio
    field_simp
    ring

/--
**Durma basıncı kaybının iki biçimi aynıdır.** Testin kurduğu biçim
(`tests/cfd/test_normal_sok.py:91`):
`P₀₂/P₀₁ = (P₂/P₁)^(−1/(γ−1)) · (ρ₂/ρ₁)^(γ/(γ−1))`
ile `quasi1d.normal_shock_relations`'ın kurduğu Anderson Eş. 3.63 biçimi
`((γ+1)m/(2+(γ−1)m))^(γ/(γ−1)) · ((γ+1)/(2γm−(γ−1)))^(1/(γ−1))`
cebirsel olarak ÖZDEŞTİR. İki bağımsız gerçekleme aynı sayıyı üretir —
`ANALITIK_Q1D_TOL_M` çapraz testinin cebirsel tabanı.
-/
theorem shockStagLoss_forms_agree {γ m : ℝ} (hγ : 1 < γ) (hm : 1 < m) :
    shockPRatio γ m ^ (-(1 / (γ - 1))) * shockRhoRatio γ m ^ (γ / (γ - 1))
      = ((γ + 1) * m / (2 + (γ - 1) * m)) ^ (γ / (γ - 1))
        * ((γ + 1) / (2 * γ * m - (γ - 1))) ^ (1 / (γ - 1)) := by
  have hγp : (0:ℝ) < γ + 1 := by linarith
  have hP : 0 < shockPRatio γ m := lt_trans one_pos (shockPRatio_gt_one hγ hm)
  have h2γ : (0:ℝ) < 2 * γ * m - (γ - 1) := by nlinarith
  have hγpne : γ + 1 ≠ 0 := ne_of_gt hγp
  have hPalt : shockPRatio γ m = (2 * γ * m - (γ - 1)) / (γ + 1) := by
    unfold shockPRatio
    field_simp
    ring
  have hPinv : (shockPRatio γ m)⁻¹ = (γ + 1) / (2 * γ * m - (γ - 1)) := by
    rw [hPalt, inv_div]
  have hbase : shockRhoRatio γ m = (γ + 1) * m / (2 + (γ - 1) * m) := by
    unfold shockRhoRatio
    ring_nf
  rw [Real.rpow_neg hP.le, ← Real.inv_rpow hP.le, hPinv, hbase, mul_comm]

/-! ## 3. HLLC ara-durum özdeşlikleri (Toro §10.4)

`hrma/cfd/riemann.py:91-93`:

```python
dl = rho_l * (s_l - un_l)
dr = rho_r * (s_r - un_r)
s_star = (p_r - p_l + un_l * dl - un_r * dr) / (dl - dr)
```

ve satır 113-119'daki star bölge durumları (Toro Eş. 10.39).
-/

/-- Ara dalga hızı `S*` — `riemann.py:93` formülünün birebir karşılığı
(Toro Eş. 10.37). -/
noncomputable def hllcSStar (ρl ul pl ρr ur pr sl sr : ℝ) : ℝ :=
  (pr - pl + ul * (ρl * (sl - ul)) - ur * (ρr * (sr - ur)))
    / (ρl * (sl - ul) - ρr * (sr - ur))

/-- Star bölge yoğunluğu `ρ*_K = ρ_K(S_K − u_K)/(S_K − S*)` — kodun `coef`
değişkeni (satır 114; Toro Eş. 10.39'un birinci bileşeni). -/
noncomputable def hllcStarRho (ρ u S s' : ℝ) : ℝ := ρ * (S - u) / (S - s')

/-- Star bölge basıncı `p* = p_K + ρ_K(S_K − u_K)(S* − u_K)` (Toro Eş. 10.36). -/
noncomputable def hllcPStar (ρ u p S s' : ℝ) : ℝ := p + ρ * (S - u) * (s' - u)

/-- Star bölge toplam enerjisi — kodun `u_star_e` ifadesi (satır 118-119):
`E*_K = ρ*_K·[E_K/ρ_K + (S* − u_K)(S* + p_K/(ρ_K(S_K − u_K)))]`
(Toro Eş. 10.39'un enerji bileşeni). -/
noncomputable def hllcStarE (ρ u p E S s' : ℝ) : ℝ :=
  hllcStarRho ρ u S s' * (E / ρ + (s' - u) * (s' + p / (ρ * (S - u))))

/--
**Payda sıfırdan uzaktır.** Einfeldt/Roe dalga hızı sıralaması altında
(`S_L < u_L` ve `u_R < S_R`; kodda `S_L ≤ u_L − a_L` ve `S_R ≥ u_R + a_R`
olduğundan sağlanır) `dl < 0 < dr`, dolayısıyla `dl − dr < 0`:
`riemann.py:93`'teki bölme dejenere olamaz.
-/
theorem hllcSStar_denom_neg {ρl ul ρr ur sl sr : ℝ}
    (hρl : 0 < ρl) (hρr : 0 < ρr) (hl : sl < ul) (hr : ur < sr) :
    ρl * (sl - ul) - ρr * (sr - ur) < 0 := by
  have h1 : ρl * (sl - ul) < 0 := mul_neg_of_pos_of_neg hρl (by linarith)
  have h2 : 0 < ρr * (sr - ur) := mul_pos hρr (by linarith)
  linarith

/--
**S\* basınç eşitliğini sağlar (Toro Eş. 10.36 → 10.37).** İki yandan
Rankine-Hugoniot ile kurulan star basınçları
`p*_K = p_K + ρ_K(S_K − u_K)(S* − u_K)` için `p*_L = p*_R` eşitliği,
`S*` kodun satır 93'teki formülüyle seçildiğinde CEBİRSEL olarak sağlanır.
HLLC'nin "temas boyunca basınç ve normal hız sürekli" varsayımının formüle
gerçekten gömülü olduğunun ispatı.
-/
theorem hllcSStar_pressure_match {ρl ul pl ρr ur pr sl sr : ℝ}
    (hne : ρl * (sl - ul) - ρr * (sr - ur) ≠ 0) :
    pl + ρl * (sl - ul) * (hllcSStar ρl ul pl ρr ur pr sl sr - ul)
      = pr + ρr * (sr - ur) * (hllcSStar ρl ul pl ρr ur pr sl sr - ur) := by
  unfold hllcSStar
  field_simp
  ring

/--
**S\* tektir.** Basınç eşitliği `S*`'da doğrusaldır; payda sıfır değilken
eşitliği sağlayan HER `s`, satır 93'teki formüle eşittir. Yani kodun formülü
Toro Eş. 10.36 sisteminin tek çözümüdür — alternatif bir "S* varyantı"
sessizce farklı fizik veremez.
-/
theorem hllcSStar_unique {ρl ul pl ρr ur pr sl sr s : ℝ}
    (hne : ρl * (sl - ul) - ρr * (sr - ur) ≠ 0)
    (h : pl + ρl * (sl - ul) * (s - ul)
       = pr + ρr * (sr - ur) * (s - ur)) :
    s = hllcSStar ρl ul pl ρr ur pr sl sr := by
  unfold hllcSStar
  rw [eq_div_iff hne]
  linear_combination h

/--
**Star durumu kütle RH koşulunu sağlar:** `ρ*S* − ρu = S(ρ* − ρ)`.
Kodun `coef` tanımının (satır 114) S_K dalgası üzerindeki kütle sıçraması
koşulundan geldiğinin doğrudan ifadesi.
-/
theorem hllcStar_mass_rh {ρ u S s' : ℝ} (hSs : S - s' ≠ 0) :
    hllcStarRho ρ u S s' * s' - ρ * u = S * (hllcStarRho ρ u S s' - ρ) := by
  unfold hllcStarRho
  field_simp
  ring

/--
**Star durumu momentum RH koşulunu sağlar:**
`(ρ*S*² + p*) − (ρu² + p) = S(ρ*S* − ρu)`.
Kodun `u_star_mn = coef·s_star` seçimi (satır 116), star basıncı Toro
Eş. 10.36'daki `p*` iken momentum sıçramasını tam sağlar.
-/
theorem hllcStar_momentum_rh {ρ u p S s' : ℝ} (hSs : S - s' ≠ 0) :
    hllcStarRho ρ u S s' * s' * s' + hllcPStar ρ u p S s' - (ρ * u * u + p)
      = S * (hllcStarRho ρ u S s' * s' - ρ * u) := by
  unfold hllcStarRho hllcPStar
  field_simp
  ring

/--
**Star durumu enerji RH koşulunu sağlar:**
`(E* + p*)S* − (E + p)u = S(E* − E)`.
Kodun satır 118-119'daki `u_star_e` ifadesi tam olarak bu koşulun çözümüdür
(Toro Eş. 10.39 enerji bileşeninin türetimi). İfadeye yazım hatası girseydi
(örn. iç çarpanlardan birinin işareti) bu özdeşlik bozulurdu.
-/
theorem hllcStar_energy_rh {ρ u p E S s' : ℝ} (hρ : ρ ≠ 0)
    (hSu : S - u ≠ 0) (hSs : S - s' ≠ 0) :
    (hllcStarE ρ u p E S s' + hllcPStar ρ u p S s') * s' - (E + p) * u
      = S * (hllcStarE ρ u p E S s' - E) := by
  unfold hllcStarE hllcStarRho hllcPStar
  field_simp
  ring

/-! ## 4. Boğulmuş debi (Anderson Eş. 5.23)

`hrma/flow/quasi1d.py:275-277`:

```python
gamma_fn = np.sqrt(g / R) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
mdot = P0 * throat_area / np.sqrt(T0) * gamma_fn
```

ve testin bağımsız kurduğu aynı formül
(`tests/cfd/test_izantropik_lule.py:78-80`).
-/

/-- Boğulmuş debi kapalı biçimi — kodun satır 275-277 formülünün birebir
karşılığı: `ṁ = P0·A*/√T0 · √(γ/R) · (2/(γ+1))^((γ+1)/(2(γ−1)))`. -/
noncomputable def chokedMassFlow (P0 T0 γ R A : ℝ) : ℝ :=
  P0 * A / Real.sqrt T0 * Real.sqrt (γ / R)
    * (2 / (γ + 1)) ^ ((γ + 1) / (2 * (γ - 1)))

/--
**TÜRETİM: kapalı biçim = ρ\*·a\*·A\*.** Sonik boğaz durumundan fiziksel
türetim: durma yoğunluğu `ρ0 = P0/(R·T0)` (ideal gaz), sonik yoğunluk
`ρ* = ρ0·(2/(γ+1))^(1/(γ−1))` (izantropik oran, M=1), sonik sıcaklık
`T* = T0·2/(γ+1)`, sonik hız `a* = √(γRT*)`. Çarpım `ρ*·a*·A*`, kodun
kapalı biçimine CEBİRSEL olarak eşittir — üsteki `(γ+1)/(2(γ−1))` ifadesi
`1/(γ−1) + 1/2` birleşiminden gelir, elle sadeleştirme hatası yoktur.
-/
theorem chokedMassFlow_derivation {γ P0 T0 R : ℝ} (hγ : 1 < γ)
    (hP : 0 < P0) (hT : 0 < T0) (hR : 0 < R) (A : ℝ) :
    P0 / (R * T0) * (2 / (γ + 1)) ^ ((1:ℝ) / (γ - 1))
      * Real.sqrt (γ * R * (T0 * (2 / (γ + 1)))) * A
    = chokedMassFlow P0 T0 γ R A := by
  have hγ0 : (0:ℝ) < γ := by linarith
  have hγ1 : (0:ℝ) < γ - 1 := by linarith
  have hγp : (0:ℝ) < γ + 1 := by linarith
  have hc : (0:ℝ) < 2 / (γ + 1) := div_pos two_pos hγp
  have hsplit : Real.sqrt (γ * R * (T0 * (2 / (γ + 1))))
      = Real.sqrt γ * Real.sqrt R * (Real.sqrt T0 * Real.sqrt (2 / (γ + 1))) := by
    rw [Real.sqrt_mul (mul_nonneg hγ0.le hR.le), Real.sqrt_mul hγ0.le,
      Real.sqrt_mul hT.le]
  have hdiv : Real.sqrt (γ / R) = Real.sqrt γ / Real.sqrt R := by
    rw [div_eq_mul_inv, Real.sqrt_mul hγ0.le, Real.sqrt_inv, div_eq_mul_inv]
  have hcs : Real.sqrt (2 / (γ + 1)) = (2 / (γ + 1)) ^ ((1:ℝ) / 2) :=
    Real.sqrt_eq_rpow _
  have hexp : (2 / (γ + 1)) ^ ((1:ℝ) / (γ - 1)) * (2 / (γ + 1)) ^ ((1:ℝ) / 2)
      = (2 / (γ + 1)) ^ ((γ + 1) / (2 * (γ - 1))) := by
    rw [← Real.rpow_add hc]
    congr 1
    field_simp
    ring
  have hRq : Real.sqrt R * Real.sqrt R = R := Real.mul_self_sqrt hR.le
  have hTq : Real.sqrt T0 * Real.sqrt T0 = T0 := Real.mul_self_sqrt hT.le
  have hRs : Real.sqrt R ≠ 0 := ne_of_gt (Real.sqrt_pos.mpr hR)
  have hTs : Real.sqrt T0 ≠ 0 := ne_of_gt (Real.sqrt_pos.mpr hT)
  unfold chokedMassFlow
  rw [hsplit, hdiv, hcs, ← hexp,
    show R * T0 = (Real.sqrt R * Real.sqrt R) * (Real.sqrt T0 * Real.sqrt T0) by
      rw [hRq, hTq]]
  field_simp

end HRMA

/-! ## Denetim: ispatların hangi aksiyomlara dayandığı

Çıktıda yalnız `propext`, `Classical.choice`, `Quot.sound` görünmeli;
`sorryAx` görünürse ispat deliklidir (`formal/check.py` bunu kapıda arar). -/

#print axioms HRMA.isentropic_state_identity
#print axioms HRMA.isentropic_process_identity
#print axioms HRMA.pRatio_strictAntiOn
#print axioms HRMA.machFromPressureRatio_recovers
#print axioms HRMA.areaRatio_at_sonic
#print axioms HRMA.shockM2sq_pos
#print axioms HRMA.shockM2sq_lt_one
#print axioms HRMA.shockM2_subsonic
#print axioms HRMA.shockPRatio_gt_one
#print axioms HRMA.shockRhoRatio_gt_one
#print axioms HRMA.shockTRatio_eq_p_div_rho
#print axioms HRMA.normalShock_satisfies_conservation
#print axioms HRMA.shockStagLoss_forms_agree
#print axioms HRMA.hllcSStar_denom_neg
#print axioms HRMA.hllcSStar_pressure_match
#print axioms HRMA.hllcSStar_unique
#print axioms HRMA.hllcStar_mass_rh
#print axioms HRMA.hllcStar_momentum_rh
#print axioms HRMA.hllcStar_energy_rh
#print axioms HRMA.chokedMassFlow_derivation
