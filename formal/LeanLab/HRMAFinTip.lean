import Mathlib

/-!
# HRMA — süpersonik kanat çarpanında **uç Mach konisi kaybı**

`hrma/analysis/six_dof_trajectory.py` içindeki `_fin_compressibility_factor`
süpersonik dalı, ÖH D24'e kadar sonlu açıklığı hiç görmeyen 2-B Ackeret
oranıydı; D24 onu sonlu-açıklık oranına çevirdi ama **uç Mach konisi
kaybını yazmadı** ve eksikliğini yalnızca ilan etti (ÖH D25 / OH-D24-03).

Ölçülen sonuç: düşük en-boylu kanatta (`AR_f = 0,25`) M = 1,5'te çarpan
`k = 4,63` çıkıyordu — kanat etkinliği sıkıştırılamaz değerin **4,6 katı**,
fiziksel olarak olanaksız.

Burada dört şey ispatlanıyor:

1. Uç Mach konisinin kayıp payı tam olarak `1/(4·β·AR_f)`'dir; koninin
   süpürdüğü üçgen ile kanat alanının oranından çıkar (`tipLoss_deficit`).
2. Kayıp çarpanı `β·AR_f ≥ 1` için `[3/4, 1)` aralığındadır ve
   `β·AR_f → ∞` iken 1'e gider: düzeltme etkinliği **asla artırmaz** ve
   2-B (sonsuz açıklık) limiti **bozmaz**.
3. Narin (Jones) kolu `D₀/2`, altsonik Diederich dalının **sonik nokta
   değeridir** (`β = 0`): kol uydurma değil, sürekliliğin kendisidir.
4. `β·AR_f = 1` geçişinde iki kolun oranı **tam `3/π`**'dir; yani
   ilan edilen %4,507'lik basamak bir kalibrasyon değil, iki bağımsız
   lineer teorinin ortak sınırdaki cebirsel farkıdır.

Ayrıca uç kayıplı dalın Mach'a göre **kesin azalan** olduğu ispatlanıyor
(`kSup_anti`): kanat etkinliği süpersonikte tekdüze düşer, salınmaz.

Sembolik (sympy) eşi: `docs/scofield/raw/OH/D25/termo-ucus/a1/turetim.py`.
-/

namespace HRMA

open Real Filter Topology

/-- **Uç Mach konisi kayıp çarpanı.** `x = β·AR_f`. Kanadın uç hücum
kenarından çıkan Mach konisinin süpürdüğü üçgende yükleme 2-B değerin
yarısıdır; kayıp payı `1/(4x)`. -/
noncomputable def tipLoss (x : ℝ) : ℝ := 1 - 1 / (4 * x)

/-- **Kayıp payının türetimi.** Üçgenin alanı `½·c·(c/β)`, içindeki
eksik yükleme oranı `½`, kanat alanı `s·c`. Dikdörtgen kanatta
`AR_f = s²/A_fin = s/c`, dolayısıyla pay `1/(4·β·AR_f)`. -/
theorem tipLoss_deficit (c s β : ℝ) (hc : 0 < c) (hs : 0 < s) (hβ : 0 < β) :
    (1 / 2 * (1 / 2 * c * (c / β))) / (s * c) = 1 / (4 * β * (s / c)) := by
  have hc' : c ≠ 0 := ne_of_gt hc
  have hs' : s ≠ 0 := ne_of_gt hs
  have hβ' : β ≠ 0 := ne_of_gt hβ
  field_simp
  ring

/-- Kayıp çarpanı 1'den **kesin küçüktür**: düzeltme kanat etkinliğini
asla artırmaz. -/
theorem tipLoss_lt_one {x : ℝ} (hx : 0 < x) : tipLoss x < 1 := by
  have : 0 < 1 / (4 * x) := by positivity
  unfold tipLoss; linarith

/-- Geçerlilik bölgesinde (`β·AR_f ≥ 1`) kayıp çarpanı en az `3/4`'tür:
düzeltme etkinliği en çok **%25** azaltır. -/
theorem tipLoss_ge_three_quarters {x : ℝ} (hx : 1 ≤ x) : 3 / 4 ≤ tipLoss x := by
  have hx0 : (0 : ℝ) < x := lt_of_lt_of_le zero_lt_one hx
  have h : 1 / (4 * x) ≤ 1 / 4 :=
    one_div_le_one_div_of_le (by norm_num) (by linarith)
  unfold tipLoss; linarith

/-- Sınırda tam `3/4`. -/
theorem tipLoss_one : tipLoss 1 = 3 / 4 := by unfold tipLoss; norm_num

/-- **2-B limit korunur:** `β·AR_f → ∞` iken kayıp çarpanı 1'e gider,
yani sonsuz açıklıkta ifade eski (Ackeret) 2-B oranına döner. -/
theorem tipLoss_tendsto_one : Tendsto tipLoss atTop (𝓝 1) := by
  have h4 : Tendsto (fun x : ℝ => 4 * x) atTop atTop :=
    Filter.Tendsto.const_mul_atTop (by norm_num) tendsto_id
  have h0 : Tendsto (fun x : ℝ => 1 / (4 * x)) atTop (𝓝 0) :=
    tendsto_const_nhds.div_atTop h4
  have h1 : Tendsto (fun _ : ℝ => (1 : ℝ)) atTop (𝓝 1) := tendsto_const_nhds
  have h2 : Tendsto (fun x : ℝ => 1 - 1 / (4 * x)) atTop (𝓝 (1 - 0)) :=
    h1.sub h0
  rw [sub_zero] at h2
  unfold tipLoss
  exact h2

/-- **Süpersonik dal, uç kaybıyla** (kodun `_k_sup` gövdesi):
`k = 2·D₀·(1 − 1/(4·β·AR))/(π·AR·β)`. -/
noncomputable def kSup (D₀ AR β : ℝ) : ℝ :=
  2 * D₀ * tipLoss (β * AR) / (π * AR * β)

/-- Uç kaybı **olmadan** (ÖH D24 hâli). -/
noncomputable def kSupNoTip (D₀ AR β : ℝ) : ℝ := 2 * D₀ / (π * AR * β)

/-- **Narin (Jones) kolu:** `C_Nα → π·A/2` ⇒ `k = D₀/2`, Mach'tan bağımsız. -/
noncomputable def kSlender (D₀ : ℝ) : ℝ := D₀ / 2

/-- **Altsonik Diederich dalı** (`β = √(1−M²)`). -/
noncomputable def kSub (D₀ Q β : ℝ) : ℝ :=
  D₀ / (1 + Real.sqrt (1 + β ^ 2 * Q ^ 2))

/-- **Onarımın yönü.** Uç kaybı yazılınca çarpan D24 hâlinden **kesin
küçük** olur: düzeltme iyimserliği giderir, yenisini üretmez. -/
theorem kSup_lt_kSupNoTip {D₀ AR β : ℝ} (hD : 0 < D₀) (hAR : 0 < AR)
    (hβ : 0 < β) : kSup D₀ AR β < kSupNoTip D₀ AR β := by
  have hx : 0 < β * AR := mul_pos hβ hAR
  have hden : 0 < π * AR * β := by positivity
  unfold kSup kSupNoTip
  rw [div_lt_div_iff_of_pos_right hden]
  nlinarith [tipLoss_lt_one hx, hD]

/-- **Sonik nokta.** Narin kol `D₀/2`, altsonik dalın `β = 0` (yani
`M = 1`) değerinin **tam kendisidir** — kol sürekli bağlanır, uydurma
sabit değildir. -/
theorem kSlender_eq_kSub_sonic (D₀ Q : ℝ) : kSlender D₀ = kSub D₀ Q 0 := by
  unfold kSlender kSub
  norm_num

/-- **Geçişteki basamak tam `3/π`'dir.** `β·AR_f = 1` sınırında uç kayıplı
dal ile narin kol arasındaki oran sabittir; ilan edilen %4,507'lik
basamak buradan gelir (`1 − 3/π = 0,0450703…`). -/
theorem kSup_threshold_ratio {D₀ AR β : ℝ} (hAR : 0 < AR) (hβ : 0 < β)
    (h : β * AR = 1) : kSup D₀ AR β = 3 / π * kSlender D₀ := by
  have hpi : (π : ℝ) ≠ 0 := Real.pi_ne_zero
  have hAR' : AR ≠ 0 := ne_of_gt hAR
  have hβ' : β ≠ 0 := ne_of_gt hβ
  have hAB : π * AR * β = π := by
    rw [mul_assoc, mul_comm AR β, h, mul_one]
  unfold kSup kSlender tipLoss
  rw [h, hAB]
  field_simp
  ring

/-- Basamak **aşağı** yönlüdür: geçişte `k` düşer, yükselmez. -/
theorem kSup_lt_kSlender_at_threshold {D₀ AR β : ℝ} (hD : 0 < D₀)
    (hAR : 0 < AR) (hβ : 0 < β) (h : β * AR = 1) :
    kSup D₀ AR β < kSlender D₀ := by
  have h3 : (3 : ℝ) / π < 1 := by
    rw [div_lt_one Real.pi_pos]
    linarith [Real.pi_gt_three]
  have hs : 0 < kSlender D₀ := by unfold kSlender; linarith
  calc kSup D₀ AR β = 3 / π * kSlender D₀ :=
        kSup_threshold_ratio hAR hβ h
    _ < 1 * kSlender D₀ := by exact mul_lt_mul_of_pos_right h3 hs
    _ = kSlender D₀ := one_mul _

/-- **Tekdüzelik.** Geçerlilik bölgesinde (`β·AR_f ≥ 1`) uç kayıplı dal
`β`'ya — dolayısıyla Mach'a — göre **kesin azalandır**: kanat etkinliği
süpersonikte tekdüze düşer, salınmaz. -/
theorem kSup_anti {D₀ AR β₁ β₂ : ℝ} (hD : 0 < D₀) (hAR : 0 < AR)
    (h₁ : 1 ≤ β₁ * AR) (hlt : β₁ < β₂) :
    kSup D₀ AR β₂ < kSup D₀ AR β₁ := by
  have hβ₁ : 0 < β₁ := by nlinarith
  have hβ₂ : 0 < β₂ := lt_trans hβ₁ hlt
  have h₂ : 1 ≤ β₂ * AR := le_trans h₁ (by nlinarith)
  have hpi : (π : ℝ) ≠ 0 := Real.pi_ne_zero
  have hAR' : AR ≠ 0 := ne_of_gt hAR
  have hb₁ : β₁ ≠ 0 := ne_of_gt hβ₁
  have hb₂ : β₂ ≠ 0 := ne_of_gt hβ₂
  have key : kSup D₀ AR β₁ - kSup D₀ AR β₂ =
      (2 * D₀ / (π * AR)) * ((β₂ - β₁) / (β₁ ^ 2 * β₂ ^ 2))
        * (β₁ * β₂ - (β₁ + β₂) / (4 * AR)) := by
    unfold kSup tipLoss
    field_simp
    ring
  have hc1 : 0 < 2 * D₀ / (π * AR) := by positivity
  have hc2 : 0 < (β₂ - β₁) / (β₁ ^ 2 * β₂ ^ 2) := by
    apply div_pos (by linarith) (by positivity)
  have hc3 : 0 < β₁ * β₂ - (β₁ + β₂) / (4 * AR) := by
    rw [sub_pos, div_lt_iff₀ (by positivity)]
    nlinarith [mul_pos hβ₁ hβ₂]
  nlinarith [mul_pos (mul_pos hc1 hc2) hc3]

/-- Çarpan geçerlilik bölgesinde **pozitiftir** (fail-closed: negatif ya da
sıfır kanat etkinliği üretmez). -/
theorem kSup_pos {D₀ AR β : ℝ} (hD : 0 < D₀) (hAR : 0 < AR)
    (h : 1 ≤ β * AR) : 0 < kSup D₀ AR β := by
  have hβ : 0 < β := by nlinarith
  have ht : 0 < tipLoss (β * AR) := by
    have := tipLoss_ge_three_quarters h
    linarith
  unfold kSup
  positivity

end HRMA
