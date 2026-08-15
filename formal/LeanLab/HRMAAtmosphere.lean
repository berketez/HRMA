import Mathlib

/-!
# HRMA — ISA katman tablosunun tutarlılığı

`hrma/constants.py:49-62` US Standard Atmosphere 1976 tablosunu parça parça
tutuyor ve `isa_temperature` katmanı seçip doğrusal ekstrapole ediyor:

```python
ISA_LAYERS = [
    (0.0,     288.15, -0.0065, 101325.0),
    (11000.0, 216.65,  0.0,    22632.1),
    (20000.0, 216.65,  0.001,  5474.89),
    (32000.0, 228.65,  0.0028, 868.019),
    (47000.0, 270.65,  0.0,    110.906),
    (51000.0, 270.65, -0.0028, 66.9389),
    (71000.0, 214.65, -0.002,  3.95642),
]
ISA_TABLE_TOP_M = 84852.0

def isa_temperature(altitude_m):
    ...
    h_base, T_base, lapse, _ = _isa_layer(h)
    return T_base + lapse * (h - h_base)
```

**Neden ispat gerekiyor.** Parçalı tanımlı bir fonksiyonda her katmanın taban
sıcaklığı, bir önceki katmanın o irtifadaki değerine EŞİT olmak zorundadır.
Değilse fonksiyon sınırda sıçrar: aynı irtifayı 10999 m ve 11001 m diye
sorduğunda farklı atmosfer alırsın, ve bu sessizce yanlış itki/sürükleme
üretir. Tablo elle yazıldığı için bu, tek bir basamak hatasıyla bozulabilir.

**Gerçekten oldu.** Faz 1 denetiminde 100 km satırının elle `T = 1000 K`
yazıldığı ölçüldü; doğru değer tablo tepesinin izotermal uzantısı olan
`186,946 K`. Aşağıda hem sınır sürekliliği hem de bu tepe değeri makine
düzeyinde doğrulanıyor.
-/

namespace HRMA

/-- ISA katmanı: taban irtifası, taban sıcaklığı, sıcaklık düşüş oranı. -/
structure ISALayer where
  hBase : ℝ
  tBase : ℝ
  lapse : ℝ

/-- Katman içi sıcaklık — `constants.py`'deki `T_base + lapse*(h - h_base)`. -/
noncomputable def layerTemp (l : ISALayer) (h : ℝ) : ℝ :=
  l.tBase + l.lapse * (h - l.hBase)

/-- `hrma/constants.py:49-57` tablosunun birebir karşılığı. -/
noncomputable def isaLayers : List ISALayer :=
  [ ⟨0,     288.15, -0.0065⟩,
    ⟨11000, 216.65,  0⟩,
    ⟨20000, 216.65,  0.001⟩,
    ⟨32000, 228.65,  0.0028⟩,
    ⟨47000, 270.65,  0⟩,
    ⟨51000, 270.65, -0.0028⟩,
    ⟨71000, 214.65, -0.002⟩ ]

/-- `hrma/constants.py:62` — tablonun geopotansiyel üst sınırı. -/
noncomputable def isaTableTop : ℝ := 84852

/--
İki katman sınırda **uyumludur**: alttaki katmanın üstteki katmanın taban
irtifasında verdiği sıcaklık, üstteki katmanın taban sıcaklığına eşittir.
Bu sağlanmazsa `isa_temperature` o irtifada sıçrar.
-/
def MatchesAt (l l' : ISALayer) : Prop := layerTemp l l'.hBase = l'.tBase

/-! ## Altı sınırın tamamı sürekli -/

theorem isa_continuous_0_11 :
    MatchesAt ⟨0, 288.15, -0.0065⟩ ⟨11000, 216.65, 0⟩ := by
  unfold MatchesAt layerTemp; norm_num

theorem isa_continuous_11_20 :
    MatchesAt ⟨11000, 216.65, 0⟩ ⟨20000, 216.65, 0.001⟩ := by
  unfold MatchesAt layerTemp; norm_num

theorem isa_continuous_20_32 :
    MatchesAt ⟨20000, 216.65, 0.001⟩ ⟨32000, 228.65, 0.0028⟩ := by
  unfold MatchesAt layerTemp; norm_num

theorem isa_continuous_32_47 :
    MatchesAt ⟨32000, 228.65, 0.0028⟩ ⟨47000, 270.65, 0⟩ := by
  unfold MatchesAt layerTemp; norm_num

theorem isa_continuous_47_51 :
    MatchesAt ⟨47000, 270.65, 0⟩ ⟨51000, 270.65, -0.0028⟩ := by
  unfold MatchesAt layerTemp; norm_num

theorem isa_continuous_51_71 :
    MatchesAt ⟨51000, 270.65, -0.0028⟩ ⟨71000, 214.65, -0.002⟩ := by
  unfold MatchesAt layerTemp; norm_num

/--
**Tablo tutarlıdır.** Ardışık her katman çifti sınırda uyumlu; dolayısıyla
`isa_temperature` katman sınırlarında sıçramaz.
-/
theorem isaLayers_all_continuous :
    MatchesAt ⟨0, 288.15, -0.0065⟩ ⟨11000, 216.65, 0⟩ ∧
    MatchesAt ⟨11000, 216.65, 0⟩ ⟨20000, 216.65, 0.001⟩ ∧
    MatchesAt ⟨20000, 216.65, 0.001⟩ ⟨32000, 228.65, 0.0028⟩ ∧
    MatchesAt ⟨32000, 228.65, 0.0028⟩ ⟨47000, 270.65, 0⟩ ∧
    MatchesAt ⟨47000, 270.65, 0⟩ ⟨51000, 270.65, -0.0028⟩ ∧
    MatchesAt ⟨51000, 270.65, -0.0028⟩ ⟨71000, 214.65, -0.002⟩ :=
  ⟨isa_continuous_0_11, isa_continuous_11_20, isa_continuous_20_32,
   isa_continuous_32_47, isa_continuous_47_51, isa_continuous_51_71⟩

/-! ## Tablo tepesi — Faz 1'de düzeltilen `1000 K` hatası -/

/--
Tablo tepesindeki (84.852 km) sıcaklık, son katmanın oraya ekstrapolasyonudur:
`214,65 − 0,002 · (84852 − 71000) = 186,946 K`.
-/
theorem isaTopTemperature :
    layerTemp ⟨71000, 214.65, -0.002⟩ isaTableTop = 186.946 := by
  unfold layerTemp isaTableTop; norm_num

/--
**Elle yazılan `1000 K` yanlıştı** ve azımsanacak bir fark değil: doğru
değerin **5 katından fazlası**. İdeal gazda ses hızı `√T` ile ölçeklendiği
için bu, o irtifadaki Mach ve sürükleme hesabını kökten bozar.
-/
theorem isaTop_not_1000 :
    layerTemp ⟨71000, 214.65, -0.002⟩ isaTableTop ≠ 1000 ∧
    5 * layerTemp ⟨71000, 214.65, -0.002⟩ isaTableTop < 1000 := by
  rw [isaTopTemperature]
  constructor <;> norm_num

/-! ## Sürekliliğin doğrudan sonucu: sınırda tek değer -/

/--
Uyumlu iki katman sınırda **aynı** sıcaklığı verir; yani `_isa_layer`'ın
sınırda hangi katmanı seçtiği sonucu değiştirmez. `isa_temperature`
`h >= candidate[0]` karşılaştırmasıyla üstteki katmanı seçiyor; bu teorem
alttakinin seçilmesi hâlinde de aynı sayının çıkacağını garantiler.
-/
theorem boundary_choice_irrelevant (l l' : ISALayer) (h : MatchesAt l l') :
    layerTemp l l'.hBase = layerTemp l' l'.hBase := by
  unfold MatchesAt at h
  unfold layerTemp at h ⊢
  simp [h]

end HRMA

/-! ## Denetim -/

#print axioms HRMA.isaLayers_all_continuous
#print axioms HRMA.isaTopTemperature
#print axioms HRMA.isaTop_not_1000
#print axioms HRMA.boundary_choice_irrelevant
