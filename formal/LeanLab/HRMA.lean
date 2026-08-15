import Mathlib

/-!
# HRMA — alan/Mach bağıntısının tekliği

`hrma/analysis/transient_ballistics.py:314-319` şunu yapıyor:

```python
def area_ratio(M):
    return (1.0 / M) * ((2.0 / (gamma + 1.0))
                        * (1.0 + (gamma - 1.0) / 2.0 * M * M)) \
           ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))) - eps
Me = brentq(area_ratio, 1.0001, 50.0)
```

`brentq` tek kök varsayar. Varsayım geçerli değilse çözücü sessizce yanlış
dala oturur. Aşağıda bu varsayımın gerekçesi — fonksiyonun süpersonik dalda
kesin monoton artan olduğu — makine düzeyinde ispatlanıyor.
-/

namespace HRMA

open Real Set

/-- Genel biçim: `M ↦ M⁻¹ · (c(1 + k M²))^e`. HRMA'nın alan oranı bunun
`c = 2/(γ+1)`, `k = (γ-1)/2`, `e = (γ+1)/(2(γ-1))` hâli. -/
noncomputable def ratio (c k e M : ℝ) : ℝ := M⁻¹ * (c * (1 + k * M ^ 2)) ^ e

section

variable {c k e M : ℝ}

/-- Parantez içi pozitif. -/
lemma inner_pos (hc : 0 < c) (hk : 0 < k) (hM : 0 < M) :
    0 < c * (1 + k * M ^ 2) := by positivity

/--
**Türev.** `2ke = k + 1` bağıntısı sağlandığında türev tam olarak
`(M² − 1)` ile orantılı çıkar. İşareti belirleyen tek şey budur.

Bu bağıntı HRMA'nın parametrelerinde kendiliğinden sağlanır:
`2·((γ−1)/2)·((γ+1)/(2(γ−1))) = (γ+1)/2 = (γ−1)/2 + 1`.
-/
lemma hasDerivAt_ratio (hc : 0 < c) (hk : 0 < k) (hM : 0 < M)
    (hke : 2 * k * e = k + 1) :
    HasDerivAt (ratio c k e)
      ((c * (1 + k * M ^ 2)) ^ (e - 1) * (c / M ^ 2) * (M ^ 2 - 1)) M := by
  have hg : (0:ℝ) < c * (1 + k * M ^ 2) := inner_pos hc hk hM
  have hM0 : M ≠ 0 := ne_of_gt hM
  -- iç fonksiyonun türevi
  have hin : HasDerivAt (fun x : ℝ => c * (1 + k * x ^ 2)) (c * (k * (2 * M))) M := by
    have : HasDerivAt (fun x : ℝ => 1 + k * x ^ 2) (k * (2 * M)) M := by
      simpa using ((hasDerivAt_pow 2 M).const_mul k).const_add 1
    simpa using this.const_mul c
  -- dış: rpow
  have hpow : HasDerivAt (fun x : ℝ => (c * (1 + k * x ^ 2)) ^ e)
      (c * (k * (2 * M)) * e * (c * (1 + k * M ^ 2)) ^ (e - 1)) M :=
    hin.rpow_const (Or.inl (ne_of_gt hg))
  -- çarpım kuralı
  have hinv : HasDerivAt (fun x : ℝ => x⁻¹) (-(M ^ 2)⁻¹) M := hasDerivAt_inv hM0
  have hmul := hinv.mul hpow
  -- türev ifadesini sadeleştir
  refine hmul.congr_deriv ?_
  have hk0 : k ≠ 0 := ne_of_gt hk
  -- `g^e = g^(e-1) · g`
  have hsplit : (c * (1 + k * M ^ 2)) ^ (e - 1) * (c * (1 + k * M ^ 2))
      = (c * (1 + k * M ^ 2)) ^ e := by
    rw [Real.rpow_sub hg, Real.rpow_one]
    field_simp
  rw [← hsplit]
  -- `2ke = k+1` bağıntısını `e` için çöz
  have he : e = (k + 1) / (2 * k) := by
    field_simp
    linear_combination hke
  rw [he]
  field_simp
  ring

/-- **Süpersonik dalda türev pozitif.** -/
lemma deriv_pos (hc : 0 < c) (hk : 0 < k) (hM : 1 < M) (hke : 2 * k * e = k + 1) :
    0 < deriv (ratio c k e) M := by
  have hM0 : (0:ℝ) < M := lt_trans one_pos hM
  have hg : (0:ℝ) < c * (1 + k * M ^ 2) := inner_pos hc hk hM0
  rw [(hasDerivAt_ratio hc hk hM0 hke).deriv]
  have h1 : (0:ℝ) < (c * (1 + k * M ^ 2)) ^ (e - 1) := Real.rpow_pos_of_pos hg _
  have h2 : (0:ℝ) < c / M ^ 2 := by positivity
  have h3 : (0:ℝ) < M ^ 2 - 1 := by nlinarith
  positivity

/-- **Kesin monoton artan.** Dolayısıyla `[1, ∞)` üzerinde en fazla bir kök vardır. -/
theorem strictMonoOn_ratio (hc : 0 < c) (hk : 0 < k) (hke : 2 * k * e = k + 1) :
    StrictMonoOn (ratio c k e) (Ici 1) := by
  apply strictMonoOn_of_deriv_pos (convex_Ici 1)
  · -- süreklilik
    apply ContinuousOn.mul (continuousOn_inv₀.mono ?_)
    · apply ContinuousOn.rpow_const
      · fun_prop
      · intro x hx
        left
        have : (0:ℝ) < x := lt_of_lt_of_le one_pos hx
        exact ne_of_gt (inner_pos hc hk this)
    · intro x hx
      exact ne_of_gt (lt_of_lt_of_le one_pos hx)
  · intro x hx
    rw [interior_Ici] at hx
    exact deriv_pos hc hk hx hke

end

/-! ## HRMA parametrelerine uygulama -/

/-- HRMA'nın alan oranı fonksiyonu (koddaki formülün birebir karşılığı). -/
noncomputable def areaRatio (γ M : ℝ) : ℝ :=
  ratio (2 / (γ + 1)) ((γ - 1) / 2) ((γ + 1) / (2 * (γ - 1))) M

/--
**Sonuç.** `γ > 1` için alan oranı `M ≥ 1` üzerinde kesin monoton artandır.

Bu, `brentq(area_ratio, 1.0001, 50.0)` çağrısının tek köke yakınsadığının
gerekçesidir: fonksiyon monoton olduğu için aralıkta en fazla bir kök vardır.
-/
theorem areaRatio_strictMonoOn (γ : ℝ) (hγ : 1 < γ) :
    StrictMonoOn (areaRatio γ) (Ici 1) := by
  have hpos : (0:ℝ) < γ - 1 := by linarith
  have hne : γ - 1 ≠ 0 := ne_of_gt hpos
  have hplus : (0:ℝ) < γ + 1 := by linarith
  have hplusne : γ + 1 ≠ 0 := ne_of_gt hplus
  apply strictMonoOn_ratio
  · exact div_pos (by norm_num) hplus
  · linarith
  · field_simp
    ring

/-- Tekliğin doğrudan ifadesi: iki kök varsa eşittirler. -/
theorem areaRatio_root_unique (γ ε : ℝ) (hγ : 1 < γ) {M₁ M₂ : ℝ}
    (h₁ : 1 ≤ M₁) (h₂ : 1 ≤ M₂)
    (e₁ : areaRatio γ M₁ = ε) (e₂ : areaRatio γ M₂ = ε) : M₁ = M₂ :=
  (areaRatio_strictMonoOn γ hγ).injOn h₁ h₂ (e₁.trans e₂.symm)

end HRMA

/-! ## Denetim: ispatın hangi aksiyomlara dayandığı

Çıktıda yalnız `propext`, `Classical.choice`, `Quot.sound` görünmeli.
`sorryAx` görünürse ispat deliklidir. -/

#print axioms HRMA.areaRatio_strictMonoOn
#print axioms HRMA.areaRatio_root_unique
