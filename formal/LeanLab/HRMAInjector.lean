import Mathlib

/-!
# HRMA — Nurick kavitasyon sayısının buhar basıncına göre yönü

`hrma/utils/injector_design.py:903-905`:

```python
k_c = (self.P_tank - self.p_vapor_bar) / max(self.P_tank - self.P_c, 1e-9)
if k_c < NURICK_KC_LIMIT:      # NURICK_KC_LIMIT = 1.5
    warn_list.append("Cavitation risk: ...")
```

Kaynak: Nurick, ASME J. Fluids Eng. 98 (1976).

**Neden ispat gerekiyor.** `p_vapor_bar` her zaman kesin bilinmez: akışkanın
kimliği, sıcaklığı ya da doyma tablosu eksik olabilir. Faz 1 denetiminde tam
olarak bu oldu — enjektör akışkan kimliğini alamadığı için yanlış `P_v`
kullanıyordu. O zaman şu soru kritik hâle gelir:

> `P_v`'yi olduğundan **küçük** tahmin edersek hata hangi yöne düşer?

Aşağıda dört şey ispatlanıyor:

1. `K_c`, `P_v`'nin **kesin azalan** fonksiyonudur.
2. Dolayısıyla `P_v` küçük tahmin edilirse `K_c` **büyük** çıkar.
3. `P_v`'yi **büyük** tahmin edip yine de eşiği geçmek **güvenlidir**:
   gerçek `K_c` de eşiğin üstündedir.
4. Ama `P_v`'yi **küçük** tahmin edip eşiği geçmek **hiçbir şey kanıtlamaz**:
   somut sayılarla, uyarının kaçırıldığı bir durum kuruluyor.

Sonuç: `p_vapor_bar` belirsizken "K_c ≥ 1.5, risk yok" çıktısı **kazanılmamış
bir hükümdür**. Hata güvensiz tarafa düşer.
-/

namespace HRMA

/-- Nurick kavitasyon sayısı: `K_c = (P₁ − P_v)/(P₁ − P₂)`.
`P₁` besleme (tank) basıncı, `P₂` oda basıncı, `P_v` buhar basıncı. -/
noncomputable def cavitationNumber (P₁ P₂ Pv : ℝ) : ℝ := (P₁ - Pv) / (P₁ - P₂)

/-- `hrma/engines/injector_design.py:64` — `FLIP_KC_LIMIT = 1.5`. -/
noncomputable def kcLimit : ℝ := 1.5

section
variable {P₁ P₂ : ℝ}

/--
**1. Kesin azalan.** Sabit `P₁ > P₂` için `K_c`, `P_v`'nin kesin azalan
fonksiyonudur.
-/
theorem cavitationNumber_strictAnti (h : P₂ < P₁) :
    StrictAnti (cavitationNumber P₁ P₂) := by
  intro a b hab
  unfold cavitationNumber
  have hd : (0 : ℝ) < P₁ - P₂ := by linarith
  gcongr

/--
**2. Küçük tahmin, büyük `K_c`.** Varsayılan buhar basıncı gerçeğinden
küçükse, hesaplanan kavitasyon sayısı gerçeğinden büyüktür.
-/
theorem underestimate_inflates_kc (h : P₂ < P₁) {PvVarsayilan PvGercek : ℝ}
    (hlt : PvVarsayilan < PvGercek) :
    cavitationNumber P₁ P₂ PvGercek < cavitationNumber P₁ P₂ PvVarsayilan :=
  cavitationNumber_strictAnti h hlt

/--
**3. Güvenli yön.** Buhar basıncını gerçeğinden **büyük** (ya da eşit) alıp
yine de eşiği geçiyorsak, gerçek `K_c` de eşiğin üstündedir. Yani
muhafazakâr `P_v` tahminiyle "risk yok" demek **kazanılmış** bir hükümdür.
-/
theorem conservative_when_overestimated (h : P₂ < P₁)
    {PvVarsayilan PvGercek : ℝ} (hge : PvGercek ≤ PvVarsayilan)
    (hpass : kcLimit ≤ cavitationNumber P₁ P₂ PvVarsayilan) :
    kcLimit ≤ cavitationNumber P₁ P₂ PvGercek := by
  refine le_trans hpass ?_
  rcases eq_or_lt_of_le hge with heq | hlt
  · exact le_of_eq (by rw [heq])
  · exact le_of_lt (cavitationNumber_strictAnti h hlt)

end

/--
**4. Güvensiz yön — eşiği geçmek hiçbir şey kanıtlamaz.**

Somut karşı örnek: `P₁ = 50 bar`, `P₂ = 20 bar`.

* Varsayılan `P_v = 4 bar`  →  `K_c = 46/30 ≈ 1,533 ≥ 1,5`  →  **uyarı yok**
* Gerçek     `P_v = 10 bar` →  `K_c = 40/30 ≈ 1,333 < 1,5`  →  **uyarı gerekli**

Yani program "kavitasyon riski yok" der, gerçekte vardır. Bu, N₂O gibi
buhar basıncı sıcaklıkla hızla değişen akışkanlarda gerçekçi bir aralıktır.
-/
theorem underestimate_can_miss_warning :
    ∃ P₁ P₂ PvVarsayilan PvGercek : ℝ,
      P₂ < P₁ ∧ PvVarsayilan < PvGercek ∧
      kcLimit ≤ cavitationNumber P₁ P₂ PvVarsayilan ∧
      cavitationNumber P₁ P₂ PvGercek < kcLimit := by
  refine ⟨50, 20, 4, 10, by norm_num, by norm_num, ?_, ?_⟩ <;>
    · unfold cavitationNumber kcLimit; norm_num

/--
**Eşik ölçütünün kapalı biçimi.** `K_c < 1,5` tam olarak
`P_v > P₁ − 1,5·(P₁ − P₂)` demektir; yani buhar basıncı için doğrudan bir
sınır. Kodun karşılaştırmasının ne anlama geldiğini bu belirler.
-/
theorem kc_below_limit_iff {P₁ P₂ Pv : ℝ} (h : P₂ < P₁) :
    cavitationNumber P₁ P₂ Pv < kcLimit ↔ P₁ - kcLimit * (P₁ - P₂) < Pv := by
  have hd : (0 : ℝ) < P₁ - P₂ := by linarith
  unfold cavitationNumber kcLimit
  rw [div_lt_iff₀ hd]
  constructor <;> intro hx <;> linarith

end HRMA

/-! ## Denetim -/

#print axioms HRMA.cavitationNumber_strictAnti
#print axioms HRMA.underestimate_inflates_kc
#print axioms HRMA.conservative_when_overestimated
#print axioms HRMA.underestimate_can_miss_warning
#print axioms HRMA.kc_below_limit_iff
