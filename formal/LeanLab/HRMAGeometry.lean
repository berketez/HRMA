import Mathlib

/-!
# HRMA — kesik koni halkasının hacmi

`hrma/engines/nozzle_design.py:838-843` şunu hesaplıyor:

```python
#   V = π·(2·t·r_ort + t²)·L
vol_conv = (np.pi * (2.0 * t_w * (r_chamber_m + rt) / 2.0 + t_w ** 2)
            * L_conv_m) if L_conv_m > 0 else 0.0
vol_div = np.pi * (2.0 * t_w * (rt + re) / 2.0 + t_w ** 2) * L_div
nozzle_mass = (vol_conv + vol_div) * rho_wall
```

Bunun öncesinde kod ince kabuk yaklaşımı (`yüzey_alanı · t · ρ`) kullanıyordu.
Aynı koşuda bu modül **0,303 kg**, çizilen CAD katısı **0,756 kg** diyordu —
tek yanıtta aynı parçaya 2,5 kat farklı iki kütle.

Aşağıda iki şey ispatlanıyor:

1. Yukarıdaki formül, cidarın iç kontura **dışarı** eklendiği düz konik
   kesik koni için **kesin** doğrudur (yaklaşım değil).
2. İnce kabuk yaklaşımı gerçek hacimden **tam olarak `π·t²·L`** kadar
   küçüktür. Yani eski hesap her zaman ve tam olarak bu terim kadar
   **eksik** tahmin ediyordu; kalın cidarda hata büyür.

`t²` terimi ikinci mertebeden diye ihmal edilebilir görünür; ölçülen
2,5 katlık fark bunun neden doğru olmadığını gösteriyor.
-/

namespace HRMA

open Real MeasureTheory intervalIntegral

/-- Kesik koninin **iç** yarıçapı: `z ∈ [0, L]` boyunca `r₁`'den `r₂`'ye
doğrusal değişir. -/
noncomputable def innerRadius (r₁ r₂ L z : ℝ) : ℝ := r₁ + (r₂ - r₁) * z / L

/-- HRMA'nın kullandığı kapalı biçim: `V = π·(2·t·r_ort + t²)·L`,
`r_ort = (r₁+r₂)/2`. -/
noncomputable def frustumAnnulusVolume (r₁ r₂ t L : ℝ) : ℝ :=
  π * (2 * t * ((r₁ + r₂) / 2) + t ^ 2) * L

/-- İnce kabuk yaklaşımı: `V ≈ 2π·r_ort·t·L` (eksen boyunca ölçülen
yanal alan × cidar). Kodun eski hâli buydu. -/
noncomputable def thinShellVolume (r₁ r₂ t L : ℝ) : ℝ :=
  2 * π * ((r₁ + r₂) / 2) * t * L

/-!
## 1. Kapalı biçim, disk integralinin tam karşılığıdır

Malzeme hacmi, her `z` kesitinde halka alanının integralidir:

`V = ∫₀^L π·(r_dış(z)² − r_iç(z)²) dz`,  `r_dış = r_iç + t`.

`(r_iç+t)² − r_iç² = 2·t·r_iç + t²` olduğundan integrand `π(2t·r_iç(z) + t²)`
olur ve `r_iç` doğrusal olduğu için ortalaması `(r₁+r₂)/2`'dir.
-/

/-- Halka alanının cebirsel özdeşliği: cidar **dışarı** eklendiğinde
kesitteki fark `2·t·r + t²`'dir. `t²` terimi buradan gelir. -/
lemma annulus_cross_section (r t : ℝ) :
    (r + t) ^ 2 - r ^ 2 = 2 * t * r + t ^ 2 := by ring

/-- Kesit alanının ters türevi: `F(z) = a·z + b·z²`,
`a = π(2t·r₁ + t²)`, `b = π·t·(r₂−r₁)/L`. -/
noncomputable def volumeAntideriv (r₁ r₂ t L z : ℝ) : ℝ :=
  (π * (2 * t * r₁ + t ^ 2)) * z + (π * t * (r₂ - r₁) / L) * z ^ 2

/-- `F' (z)` gerçekten `z` kesitindeki halka alanıdır. -/
lemma hasDerivAt_volumeAntideriv (r₁ r₂ t L : ℝ) (hL : L ≠ 0) (z : ℝ) :
    HasDerivAt (volumeAntideriv r₁ r₂ t L)
      (π * (2 * t * innerRadius r₁ r₂ L z + t ^ 2)) z := by
  have h := ((hasDerivAt_id z).const_mul (π * (2 * t * r₁ + t ^ 2))).add
      ((hasDerivAt_pow 2 z).const_mul (π * t * (r₂ - r₁) / L))
  refine h.congr_deriv ?_
  unfold innerRadius
  field_simp
  ring

/-- Kesit alanı `z`'ye göre süreklidir (integrallenebilirlik için). -/
lemma continuous_crossSection (r₁ r₂ t L : ℝ) (_hL : L ≠ 0) :
    Continuous fun z : ℝ => π * (2 * t * innerRadius r₁ r₂ L z + t ^ 2) := by
  unfold innerRadius
  fun_prop (disch := assumption)

/--
**Ana sonuç 1.** HRMA'nın kapalı biçimi, disk integraliyle **birebir**
aynıdır. Yani `nozzle_design.py`'deki formül bu geometri için bir yaklaşım
değil, kesin değerdir.
-/
theorem frustumAnnulusVolume_eq_integral (r₁ r₂ t L : ℝ) (hL : 0 < L) :
    ∫ z in (0 : ℝ)..L, π * (2 * t * innerRadius r₁ r₂ L z + t ^ 2)
      = frustumAnnulusVolume r₁ r₂ t L := by
  have hL0 : L ≠ 0 := ne_of_gt hL
  rw [intervalIntegral.integral_eq_sub_of_hasDerivAt
        (fun z _ => hasDerivAt_volumeAntideriv r₁ r₂ t L hL0 z)
        ((continuous_crossSection r₁ r₂ t L hL0).intervalIntegrable _ _)]
  unfold volumeAntideriv frustumAnnulusVolume
  field_simp
  ring

/-!
## 2. İnce kabuk yaklaşımının hatası tam olarak `π·t²·L`
-/

/--
**Ana sonuç 2.** Fark tam olarak `π·t²·L`'dir — ne fazla ne eksik.
-/
theorem frustum_minus_thinShell (r₁ r₂ t L : ℝ) :
    frustumAnnulusVolume r₁ r₂ t L - thinShellVolume r₁ r₂ t L
      = π * t ^ 2 * L := by
  unfold frustumAnnulusVolume thinShellVolume
  ring

/--
**Yön.** Pozitif cidar ve pozitif uzunlukta ince kabuk yaklaşımı
gerçek hacimden **kesin küçüktür**. Hata rastgele değil, tek yönlüdür:
eski kod kütleyi her zaman **eksik** veriyordu.
-/
theorem thinShell_lt_frustum (r₁ r₂ t L : ℝ) (ht : 0 < t) (hL : 0 < L) :
    thinShellVolume r₁ r₂ t L < frustumAnnulusVolume r₁ r₂ t L := by
  have h : (0 : ℝ) < π * t ^ 2 * L := by positivity
  have := frustum_minus_thinShell r₁ r₂ t L
  linarith

/--
**Bağıl hata.** İnce kabuğun eksikliğinin gerçek hacme oranı
`t² / (2·t·r_ort + t²)`'dir; yani cidar/yarıçap oranı büyüdükçe büyür.
Bu, "ikinci mertebeden, ihmal edilebilir" savunmasının neden yanlış
olduğunun kapalı biçimi.
-/
theorem thinShell_relative_error (r₁ r₂ t L : ℝ) (ht : 0 < t) (hL : 0 < L)
    (hr : 0 < (r₁ + r₂) / 2) :
    (frustumAnnulusVolume r₁ r₂ t L - thinShellVolume r₁ r₂ t L)
        / frustumAnnulusVolume r₁ r₂ t L
      = t ^ 2 / (2 * t * ((r₁ + r₂) / 2) + t ^ 2) := by
  rw [frustum_minus_thinShell]
  unfold frustumAnnulusVolume
  have hden : (0 : ℝ) < 2 * t * ((r₁ + r₂) / 2) + t ^ 2 := by positivity
  have hL0 : L ≠ 0 := ne_of_gt hL
  have hπ : π ≠ 0 := ne_of_gt pi_pos
  have hden0 : 2 * t * ((r₁ + r₂) / 2) + t ^ 2 ≠ 0 := ne_of_gt hden
  field_simp

end HRMA

/-! ## Denetim -/

#print axioms HRMA.frustumAnnulusVolume_eq_integral
#print axioms HRMA.frustum_minus_thinShell
#print axioms HRMA.thinShell_lt_frustum
#print axioms HRMA.thinShell_relative_error
