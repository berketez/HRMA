import Mathlib

/-!
# HRMA — ASME VIII-2 Ek 5-A gerilme lineerleştirmesinin cebri

`hrma/fea/structural_axisym.py:scl_lineerlestirme` cidar boyu bir SCL
(stress classification line) kurup şunları hesaplıyor:

```python
#   σ_m = (1/t)∫σ dx ,  σ_b = (6/t²)∫σ(t/2 − x) dx
s_m = i_sigma.sum(axis=1) / tt
s_b = 6.0 / (tt ** 2) * (c_eksi_x0 * i_sigma - i_sigma_s).sum(axis=1)
```

ve hükmü (`max_von_mises_hukum`) HAM TEPEDEN değil bu iki büyüklükten alıyor
(OH-D24-01). ÖH D26 a2'nin ölçümü bunun neden zorunlu olduğunu gösterdi
(`docs/scofield/raw/OH/D26/fea-cfd/a2/once_a2.json`, katı örnek motor,
tekdüze merdiven 64×4 → 512×32):

```
ham tepe (ASME "F")   188,49 → 211,67 → 233,06 → 242,78 MPa   (durmuyor)
hüküm (SCL P_L+P_b)   190,42 → 192,33 → 195,14 → 195,64 MPa   (duruyor)
```

Aşağıda bu ayrımın CEBİRSEL sebebi ispatlanıyor:

1. **Lineer alanda tam geri verme.** σ afin ise lineerleştirme σ'yı aynen
   geri verir (uçlarda σ(0) ve σ(t)). Yani lineerleştirme bir yaklaşım
   değil, afin bileşenin TAM ayrıştırmasıdır.
2. **L¹ sınırı.** `|σ_m| ≤ (1/t)‖σ‖₁` ve `|σ_b| ≤ (3/t)‖σ‖₁`.
   Lineerleştirme σ'nın **integraliyle** sınırlıdır, **supremumuyla**
   değil.
3. **Sonuç.** Williams (1952) köşe tekilliğinde σ ~ r^(λ−1), λ ∈ (0,1)
   INTEGRALLENEBİLİRDİR: sup ıraksarken ‖σ‖₁ sonlu kalır, dolayısıyla
   (2) gereği σ_m ve σ_b de sonlu kalır. Ham tepenin ıraksaması hükmü
   BOZAMAZ — kod bunu varsayıyordu, burada ispatlanıyor.

**DURUM:** ÖH D26 a2 ajanı yazdı (makine ile doğrulayamadı); ana model (Fable, 7 Eyl
2026 15:2x) ana ağacın Mathlib önbelleğiyle `lake env lean` ile derledi — ilk sürümde
7 hata (integral_affine/integral_affine_moment: `simp` ilerlemedi, `fun_prop`
IntervalIntegrable üretmiyor; `ring` hedefsiz), ispatlar yeniden yazıldı, 0 hata / 0 uyarı /
0 sorry. Aşağıdaki eski not tarihsel kayıttır. ESKİ NOT: bu dosya YAZILDI ama o aşamada
MAKİNE İLE DOĞRULANMADI. `formal/.lake` (≈7 GB Mathlib önbelleği)
`.gitignore`'dadır ve yalnız ana ağaçta (`/Users/apple/HRMA/formal/.lake`)
mevcuttur; bu ajanın ana ağaca dokunması yasaktır, worktree'de Mathlib
derlenmemiştir ve `lake exe cache get` ağdan indirme gerektirir. Bu yüzden
dosya `formal/LeanLab/` altına KONMADI, `LeanLab.lean`'e import EDİLMEDİ ve
`formal/registry.json`'a EKLENMEDİ — doğrulanmamış bir teorem mevcut
`formal/check.py` kapısını kırardı. Aynı üç önerme bu arada ÜRÜN KODU
üzerinde makine ile sınanıyor:
`tests/test_d26_fea_cfd_a2.py::TestSCLLineerlestirmeCebri`.

Ana modelin doğrulama adımı:
`cp HRMASCL.lean formal/LeanLab/` → `LeanLab.lean`'e `import LeanLab.HRMASCL`
→ `registry.json` girdisi → `python3 formal/check.py`.
-/

namespace HRMA.SCL

open intervalIntegral MeasureTheory

variable {t : ℝ}

/-- Membran (eşdeğer birincil) gerilme: `σ_m = (1/t)·∫₀ᵗ σ`. -/
noncomputable def sigmaM (σ : ℝ → ℝ) (t : ℝ) : ℝ :=
  (1 / t) * ∫ x in (0:ℝ)..t, σ x

/-- Eğilme gerilmesi: `σ_b = (6/t²)·∫₀ᵗ σ(x)·(t/2 − x) dx`. -/
noncomputable def sigmaB (σ : ℝ → ℝ) (t : ℝ) : ℝ :=
  (6 / t ^ 2) * ∫ x in (0:ℝ)..t, σ x * (t / 2 - x)

/-- Lineerleştirilmiş alan: `σ_lin(x) = σ_m + σ_b·(1 − 2x/t)`.
`x = 0`'da `σ_m + σ_b`, `x = t`'de `σ_m − σ_b` verir — ASME Ek 5-A'nın
"SCL uçlarında `σ_m ± σ_b`" kuralı. -/
noncomputable def sigmaLin (σ : ℝ → ℝ) (t x : ℝ) : ℝ :=
  sigmaM σ t + sigmaB σ t * (1 - 2 * x / t)

/-! ## 1. Afin alanda TAM geri verme -/

/-- `∫₀ᵗ (a + b·x) dx = a·t + b·t²/2`. -/
theorem integral_affine (a b t : ℝ) :
    (∫ x in (0:ℝ)..t, (a + b * x)) = a * t + b * t ^ 2 / 2 := by
  have h1 : IntervalIntegrable (fun _ : ℝ => a) volume 0 t := intervalIntegrable_const
  have h2 : IntervalIntegrable (fun x : ℝ => b * x) volume 0 t :=
    (by fun_prop : Continuous (fun x : ℝ => b * x)).intervalIntegrable _ _
  rw [intervalIntegral.integral_add h1 h2, intervalIntegral.integral_const,
    intervalIntegral.integral_const_mul, integral_id]
  simp
  ring

/-- `∫₀ᵗ (a + b·x)·(t/2 − x) dx = −b·t³/12`. Sabit terim düşer: `(t/2 − x)`
aralık üzerinde sıfır ortalamalıdır. -/
theorem integral_affine_moment (a b t : ℝ) :
    (∫ x in (0:ℝ)..t, (a + b * x) * (t / 2 - x)) = -(b * t ^ 3 / 12) := by
  have h : (fun x : ℝ => (a + b * x) * (t / 2 - x))
      = fun x => a * (t / 2) + ((b * (t / 2) - a) * x + (-b) * x ^ 2) := by
    funext x; ring
  rw [h]
  have hc : IntervalIntegrable (fun _ : ℝ => a * (t / 2)) volume 0 t :=
    intervalIntegrable_const
  have hx : IntervalIntegrable (fun x : ℝ => (b * (t / 2) - a) * x) volume 0 t :=
    (by fun_prop : Continuous (fun x : ℝ => (b * (t / 2) - a) * x)).intervalIntegrable _ _
  have hx2 : IntervalIntegrable (fun x : ℝ => (-b) * x ^ 2) volume 0 t :=
    (by fun_prop : Continuous (fun x : ℝ => (-b) * x ^ 2)).intervalIntegrable _ _
  rw [intervalIntegral.integral_add hc (hx.add hx2), intervalIntegral.integral_add hx hx2,
    intervalIntegral.integral_const, intervalIntegral.integral_const_mul,
    intervalIntegral.integral_const_mul, integral_id, integral_pow]
  simp
  ring

/-- **Teorem 1 (afin alanda tam geri verme).** `σ(x) = a + b·x` ise
`σ_m = a + b·t/2` ve `σ_b = −b·t/2`; dolayısıyla SCL uçlarında
`σ_m + σ_b = σ(0)` ve `σ_m − σ_b = σ(t)`. Lineerleştirme afin alanı
BOZMADAN geri verir — bekçi:
`tests/test_d26_fea_cfd_a2.py::TestSCLLineerlestirmeCebri::test_LINEER_alanda_TAM_geri_verir`. -/
theorem linearization_exact_on_affine (a b t : ℝ) (ht : t ≠ 0) :
    sigmaM (fun x => a + b * x) t = a + b * t / 2 ∧
    sigmaB (fun x => a + b * x) t = -(b * t / 2) := by
  constructor
  · unfold sigmaM
    rw [integral_affine]
    field_simp
    try ring
  · unfold sigmaB
    rw [integral_affine_moment]
    field_simp
    try ring

/-- Teorem 1'in ASME biçimi: uç değerler alanın kendi uç değerleridir. -/
theorem linearization_endpoints_affine (a b t : ℝ) (ht : t ≠ 0) :
    sigmaLin (fun x => a + b * x) t 0 = a ∧
    sigmaLin (fun x => a + b * x) t t = a + b * t := by
  obtain ⟨hm, hb⟩ := linearization_exact_on_affine a b t ht
  constructor <;> (unfold sigmaLin; rw [hm, hb]; field_simp; try ring)

/-! ## 2. L¹ sınırı — lineerleştirme SUP ile değil İNTEGRAL ile sınırlıdır -/

/-- **Teorem 2a.** `|σ_m| ≤ (1/t)·∫₀ᵗ |σ|`. -/
theorem abs_sigmaM_le (σ : ℝ → ℝ) (ht : 0 < t)
    (_hσ : IntervalIntegrable σ volume 0 t) :
    |sigmaM σ t| ≤ (1 / t) * ∫ x in (0:ℝ)..t, |σ x| := by
  unfold sigmaM
  rw [abs_mul, abs_of_pos (by positivity : (0:ℝ) < 1 / t)]
  gcongr
  exact intervalIntegral.abs_integral_le_integral_abs ht.le

/-- **Teorem 2b.** `|σ_b| ≤ (3/t)·∫₀ᵗ |σ|`.

Çekirdek: `[0, t]` üzerinde `|t/2 − x| ≤ t/2`, dolayısıyla
`|∫ σ·(t/2 − x)| ≤ (t/2)·∫|σ|` ve `6/t² · (t/2) = 3/t`. -/
theorem abs_sigmaB_le (σ : ℝ → ℝ) (ht : 0 < t)
    (hσ : IntervalIntegrable σ volume 0 t) :
    |sigmaB σ t| ≤ (3 / t) * ∫ x in (0:ℝ)..t, |σ x| := by
  have hker : ∀ x ∈ Set.uIcc (0:ℝ) t, |σ x * (t / 2 - x)| ≤ (t / 2) * |σ x| := by
    intro x hx
    rw [Set.uIcc_of_le ht.le] at hx
    rw [abs_mul, mul_comm]
    gcongr
    rw [abs_le]
    constructor <;> [linarith [hx.2]; linarith [hx.1]]
  have h1 : |∫ x in (0:ℝ)..t, σ x * (t / 2 - x)|
      ≤ ∫ x in (0:ℝ)..t, (t / 2) * |σ x| := by
    refine le_trans (intervalIntegral.abs_integral_le_integral_abs ht.le) ?_
    apply intervalIntegral.integral_mono_on ht.le
    · exact (hσ.mul_continuousOn (by fun_prop)).abs
    · exact (hσ.abs.const_mul _)
    · intro x hx; exact hker x (by rw [Set.uIcc_of_le ht.le]; exact hx)
  unfold sigmaB
  rw [abs_mul, abs_of_pos (by positivity : (0:ℝ) < 6 / t ^ 2)]
  rw [intervalIntegral.integral_const_mul] at h1
  calc 6 / t ^ 2 * |∫ x in (0:ℝ)..t, σ x * (t / 2 - x)|
      ≤ 6 / t ^ 2 * ((t / 2) * ∫ x in (0:ℝ)..t, |σ x|) := by gcongr
    _ = (3 / t) * ∫ x in (0:ℝ)..t, |σ x| := by field_simp; ring

/-- **Teorem 2 (sonuç).** SCL uç değerlerinin büyüklüğü `‖σ‖₁` ile
sınırlıdır: `|σ_m| + |σ_b| ≤ (4/t)·∫₀ᵗ|σ|`.

Sağ taraf σ'nın SUPREMUMUNU İÇERMEZ. Bu yüzden integrallenebilir bir
tekillik (Williams 1952: `σ ~ r^(λ−1)`, `λ ∈ (0,1)`, `∫₀ᵗ r^(λ−1) dr =
t^λ/λ < ∞`) supremumu ıraksatsa bile hüküm büyüklüğünü ıraksatamaz.
`hrma/fea/bridge.py`'nin "kapı hüküm büyüklüğünü ölçer, ham tepeyi değil"
kararının (OH-D16-01 / OH-D24-01) cebirsel gerekçesi budur. -/
theorem scl_bounded_by_L1 (σ : ℝ → ℝ) (ht : 0 < t)
    (hσ : IntervalIntegrable σ volume 0 t) :
    |sigmaM σ t| + |sigmaB σ t| ≤ (4 / t) * ∫ x in (0:ℝ)..t, |σ x| := by
  have hM := abs_sigmaM_le σ ht hσ
  have hB := abs_sigmaB_le σ ht hσ
  have : (1 / t) * (∫ x in (0:ℝ)..t, |σ x|) + (3 / t) * (∫ x in (0:ℝ)..t, |σ x|)
      = (4 / t) * ∫ x in (0:ℝ)..t, |σ x| := by ring
  linarith [hM, hB, this.ge, this.le]

end HRMA.SCL
