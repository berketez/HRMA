# Biçimsel ispatlar — Lean 4 / Mathlib

**Konum:** `~/Desktop/dosyalar/lean-lab` · **Kayıt:** `HRMA_ISPATLARI.md`
**Tarih:** 2 Ağustos 2026 · Lean 4.32.2, Mathlib v4.32.2 (pinli)

HRMA'nın çözücülerine verilen bazı varsayımlar yorum satırında yazılıydı ama
hiçbir yerde denetlenmiyordu: "bu fonksiyonun tek kökü var", "bu formül kesin",
"bu tablo sürekli". Yanlışlarsa çözücü sessizce yanlış dala oturur — test
yeşil kalır, sayı yanlış çıkar.

19 teorem bu varsayımları makine düzeyinde doğruluyor. Hiçbirinde `sorryAx`
yok; `#print axioms` çıktısı hepsinde `[propext, Classical.choice, Quot.sound]`.

## Hangi teorem hangi satırı koruyor

| Kod | Varsayım | Teorem |
|---|---|---|
| `analysis/transient_ballistics.py:314-319` | `brentq` aralıkta tek kök varsayar | `HRMA.areaRatio_strictMonoOn`, `areaRatio_root_unique` |
| aynı satır, `1.0001` alt sınırı | Subsonik kök bracket'e girmemeli | `HRMA.areaRatio_strictAntiOn`, `bracket_excludes_subsonic` |
| `engines/nozzle_design.py:838-843` | `V = π(2·t·r_ort + t²)·L` kesin | `HRMA.frustumAnnulusVolume_eq_integral` |
| aynı satır | İnce kabuğun hatası `π·t²·L`, tek yönlü | `HRMA.frustum_minus_thinShell`, `thinShell_lt_frustum` |
| `constants.py:49-62` | ISA katmanları sınırda sürekli | `HRMA.isaLayers_all_continuous` |
| `constants.py:62` | Tablo tepesi 186,946 K (1000 K değil) | `HRMA.isaTopTemperature`, `isaTop_not_1000` |
| `utils/injector_design.py:903-905` | `P_v` belirsizken hata güvensiz tarafa düşer | `HRMA.underestimate_can_miss_warning`, `conservative_when_overestimated` |

## Çalıştırma

```bash
cd ~/Desktop/dosyalar/lean-lab && lake build
```

Çıktıda `sorryAx` görünmemeli. `LeanLab/Basic.lean:43`'teki tek `sorry`
kuruluma ait kasıtlı bir alıştırma hedefidir, HRMA ispatlarıyla ilgisi yoktur.

## Sınır

Lean ile Python arasında **otomatik bağ yoktur**. Bağ, Lean dosyalarının
başındaki kod alıntısı ve satır numarasıdır ve **elle** korunur. İspatlar,
Lean'de yeniden yazılmış ifadelerin doğruluğunu gösterir; Python'un o ifadeyi
doğru uyguladığı ayrıca test paketiyle sınanır. Fiziksel modelin kendisi
(örneğin "Nurick ölçütü doğru ölçüttür") bir deney sorusudur, ispat sorusu
değildir. Kayan nokta aritmetiği modellenmez.
