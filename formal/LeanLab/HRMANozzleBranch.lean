import LeanLab.HRMA

/-!
# HRMA — `brentq` alt sınırının (`1.0001`) gerekçesi

`hrma/analysis/transient_ballistics.py:314-319`:

```python
Me = brentq(area_ratio, 1.0001, 50.0)
```

`LeanLab/HRMA.lean` alan oranının `[1, ∞)` üzerinde **kesin monoton artan**
olduğunu ispatladı; bu, aralıkta en fazla bir kök bulunduğunu verir. Ama
alt sınırın neden `1` değil de `1.0001` seçildiğini açıklamaz.

Sebep şu: aynı fonksiyon `(0, 1]` üzerinde **kesin monoton azalan**dır.
Yani `M = 1` bir dönüm noktasıdır ve tipik bir `ε > 1` değeri için denklemin
**iki** kökü vardır — biri subsonik, biri süpersonik. Lülenin diverjan
bölümünde fiziksel olan süpersonik olandır. Aralığın `1`'in kesin üstünde
başlaması, subsonik kökün bracket'e girmesini engeller.

Bu dosya o ikinci dalı ispatlıyor; böylece `1.0001` bir "sihirli sayı" değil,
ispatlanmış bir dal ayrımının sayısal karşılığı olur.
-/

namespace HRMA

open Real Set

section
variable {c k e M : ℝ}

/-- **Subsonik dalda türev negatif.** İşareti belirleyen `(M² − 1)` çarpanı
`M < 1` için negatiftir. -/
lemma deriv_neg (hc : 0 < c) (hk : 0 < k) (hM0 : 0 < M) (hM1 : M < 1)
    (hke : 2 * k * e = k + 1) :
    deriv (ratio c k e) M < 0 := by
  have hg : (0 : ℝ) < c * (1 + k * M ^ 2) := inner_pos hc hk hM0
  rw [(hasDerivAt_ratio hc hk hM0 hke).deriv]
  have h1 : (0 : ℝ) < (c * (1 + k * M ^ 2)) ^ (e - 1) := Real.rpow_pos_of_pos hg _
  have h2 : (0 : ℝ) < c / M ^ 2 := by positivity
  have h3 : M ^ 2 - 1 < 0 := by nlinarith
  have h4 : (0 : ℝ) < (c * (1 + k * M ^ 2)) ^ (e - 1) * (c / M ^ 2) := by positivity
  exact mul_neg_of_pos_of_neg h4 h3

/-- **Kesin monoton azalan.** `(0, 1]` üzerinde en fazla bir kök vardır —
ve bu kök süpersonik köke eşit değildir. -/
theorem strictAntiOn_ratio (hc : 0 < c) (hk : 0 < k) (hke : 2 * k * e = k + 1) :
    StrictAntiOn (ratio c k e) (Ioc 0 1) := by
  apply strictAntiOn_of_deriv_neg (convex_Ioc 0 1)
  · apply ContinuousOn.mul (continuousOn_inv₀.mono ?_)
    · apply ContinuousOn.rpow_const
      · fun_prop
      · intro x hx
        left
        exact ne_of_gt (inner_pos hc hk hx.1)
    · intro x hx
      exact ne_of_gt hx.1
  · intro x hx
    rw [interior_Ioc] at hx
    exact deriv_neg hc hk hx.1 hx.2 hke

end

/-! ## HRMA parametrelerine uygulama -/

/-- Alan oranı subsonik dalda kesin monoton azalandır. -/
theorem areaRatio_strictAntiOn (γ : ℝ) (hγ : 1 < γ) :
    StrictAntiOn (areaRatio γ) (Ioc 0 1) := by
  have hplus : (0 : ℝ) < γ + 1 := by linarith
  have hne : γ - 1 ≠ 0 := ne_of_gt (by linarith : (0 : ℝ) < γ - 1)
  have hplusne : γ + 1 ≠ 0 := ne_of_gt hplus
  apply strictAntiOn_ratio
  · exact div_pos (by norm_num) hplus
  · linarith
  · field_simp
    ring

/-- Subsonik kök de tektir. -/
theorem areaRatio_subsonic_root_unique (γ ε : ℝ) (hγ : 1 < γ) {M₁ M₂ : ℝ}
    (h₁ : M₁ ∈ Ioc (0 : ℝ) 1) (h₂ : M₂ ∈ Ioc (0 : ℝ) 1)
    (e₁ : areaRatio γ M₁ = ε) (e₂ : areaRatio γ M₂ = ε) : M₁ = M₂ :=
  (areaRatio_strictAntiOn γ hγ).injOn h₁ h₂ (e₁.trans e₂.symm)

/--
**Bracket'in gerekçesi.** Subsonik bir kök ile süpersonik bir kök **asla
aynı sayı değildir**: biri `1`'in altında (ya da tam `1`), diğeri `1`'in
üstünde olamaz — ancak ikisi de `M = 1`'e eşitse çakışırlar.

`brentq`'nun alt sınırı `1`'in **kesin üstünde** seçildiği için, aralık
subsonik dalın tamamını dışarıda bırakır; bulunan kök süpersonik olandır.
Kod bu yüzden `1` değil `1.0001` kullanıyor.
-/
theorem branches_disjoint {M_sub M_sup : ℝ}
    (hsub : M_sub ∈ Ioc (0 : ℝ) 1) (hsup : 1 < M_sup) : M_sub ≠ M_sup := by
  intro h
  have : M_sub ≤ 1 := hsub.2
  linarith [h ▸ hsup]

/--
Aralık `[a, b]` ile `1 < a` seçildiğinde subsonik dalın hiçbir noktası
bracket içinde değildir. `brentq(area_ratio, 1.0001, 50.0)` çağrısının
neden yalnız süpersonik kökü döndürdüğünün doğrudan ifadesi.
-/
theorem bracket_excludes_subsonic {a b M : ℝ} (ha : 1 < a)
    (hM : M ∈ Ioc (0 : ℝ) 1) : M ∉ Icc a b := by
  intro hmem
  have h1 : a ≤ M := hmem.1
  have h2 : M ≤ 1 := hM.2
  linarith

end HRMA

/-! ## Denetim -/

#print axioms HRMA.areaRatio_strictAntiOn
#print axioms HRMA.areaRatio_subsonic_root_unique
#print axioms HRMA.branches_disjoint
#print axioms HRMA.bracket_excludes_subsonic
