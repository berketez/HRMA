# Biçimsel ispatlar — Lean 4 / Mathlib

**Konum:** `formal/` (depo içi) · **Kayıt defteri:** `formal/registry.json`
**Ayrıntılı kayıt:** `formal/HRMA_ISPATLARI.md` (2 Ağustos 2026 anlık görüntüsü)
**Güncelleme:** 14 Ağustos 2026 · Lean 4.32.2, Mathlib v4.32.2 (pinli, `formal/lean-toolchain` + `formal/lake-manifest.json`)

HRMA'nın çözücülerine verilen bazı varsayımlar yorum satırında yazılıydı ama
hiçbir yerde denetlenmiyordu: "bu fonksiyonun tek kökü var", "bu formül kesin",
"bu tablo sürekli". Yanlışlarsa çözücü sessizce yanlış dala oturur — test
yeşil kalır, sayı yanlış çıkar.

Kayıt defterindeki 19 teorem bu varsayımları makine düzeyinde doğruluyor
(yardımcı lemmalarla birlikte `formal/LeanLab/` altında 34 bildirim).
Hiçbirinde `sorryAx` yok; 14 Ağustos 2026'da depo içinde `lake build`
çalıştırıldı ve 19 teoremin tamamının `#print axioms` çıktısı
`[propext, Classical.choice, Quot.sound]` olarak ölçüldü.

## Hangi teorem hangi satırı koruyor

Satır numaraları 14 Ağustos 2026'da ölçüldü; makine-okunur ve denetlenen tek
kaynak `formal/registry.json`'dur (satır kayarsa `formal/check.py` yakalar).

| Kod | Varsayım | Teorem |
|---|---|---|
| `hrma/analysis/transient_ballistics.py:336` | `brentq` aralıkta tek kök varsayar | `HRMA.areaRatio_strictMonoOn`, `areaRatio_root_unique` |
| aynı satır, `1.0001` alt sınırı | Subsonik kök bracket'e girmemeli | `HRMA.areaRatio_strictAntiOn`, `areaRatio_subsonic_root_unique`, `branches_disjoint`, `bracket_excludes_subsonic` |
| `hrma/engines/nozzle_design.py:844-846` | `V = π(2·t·r_ort + t²)·L` kesin | `HRMA.frustumAnnulusVolume_eq_integral` |
| aynı satırlar | İnce kabuğun hatası `π·t²·L`, tek yönlü | `HRMA.frustum_minus_thinShell`, `thinShell_lt_frustum`, `thinShell_relative_error` |
| `hrma/constants.py:49-62` | ISA katmanları sınırda sürekli | `HRMA.isaLayers_all_continuous`, `boundary_choice_irrelevant` |
| `hrma/constants.py:62,90` | Tablo tepesi 186,946 K (1000 K değil) | `HRMA.isaTopTemperature`, `isaTop_not_1000` |
| `hrma/utils/injector_design.py:1096-1098` | `P_v` belirsizken hata güvensiz tarafa düşer | `HRMA.cavitationNumber_strictAnti`, `underestimate_inflates_kc`, `underestimate_can_miss_warning`, `conservative_when_overestimated`, `kc_below_limit_iff` |

## Çalıştırma

```bash
cd formal
lake exe cache get   # yalnız ilk kurulumda (Mathlib önbelleği; atlanırsa saatler)
lake build
```

Tam denetim — derleme + `sorryAx` taraması + registry bağ denetimi, çıkış
kodu 0/1:

```bash
python3 formal/check.py
```

Çıktıda `sorryAx` görünmemeli. (Eski çalışma alanındaki `Basic.lean`'in
kasıtlı `sorry` alıştırması depoya bilinçli olarak **taşınmadı**; `formal/`
içinde kasıtlı delik yoktur.)

## Kayıt defteri ve kapı

* `formal/registry.json` — her teoremi koruduğu Python satırına bağlayan
  makine-okunur kayıt: `{theorem, lean_file, lean_line, python_file,
  python_line, anchor, claim_tr, claim_en, status}`.
* `formal/check.py` — (1) `lake build`, (2) registry'deki her teorem için
  `#print axioms` (delik/`sorryAx` denetimi), (3) her Lean ve Python satır
  referansının yerinde durduğunun denetimi. Elle tutulan bağın sessizce
  çürümesini engeller; satır kaydıysa yeni satırı önerir.

## Sınır

İspatlar, Lean'de yeniden yazılmış ifadelerin doğruluğunu gösterir; Python'un
o ifadeyi doğru uyguladığı ayrıca test paketiyle sınanır. `check.py`'nin
denetlediği bağ **konumsaldır** (dosya + satır + satır içeriği), anlamsal
değildir. Fiziksel modelin kendisi (örneğin "Nurick ölçütü doğru ölçüttür")
bir deney sorusudur, ispat sorusu değildir. Kayan nokta aritmetiği
modellenmez; teoremler ℝ üzerinde geçerlidir. Ayrıntı: `formal/README.md`,
"Neyi KANITLAMIYOR" bölümü.
