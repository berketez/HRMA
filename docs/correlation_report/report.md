# HRMA validation: correlation report

Generated: 2026-07-18T22:23:24

Auto-generated numbers; narrative added by authors.

## Overview

- Runner version: 1 (adapter 1, report 1)
- Records in statistics pipeline: 199 (synthetic excluded: 0)
- DB content hash: `c64e8d7b715bbc1dfffddcb9cc38989015685dfe6b5ff3b1026ec032ae1800bd`
- Main cells: 9 | low-confidence cells: 0 | anomaly entries: 34
- Status counts: insufficient_inputs=112, not_supported=7, ok=80

## Confidence layers

- Main (high + medium): drives the headline statistics; drawn as filled blue markers in parity figures.
- Low-confidence: reported separately, kept out of the headline statistics (see detailed tables).
- Anomaly-flagged: excluded from statistics; drawn as open orange markers so they stay visible without biasing the numbers.
- Outliers (|error - median| > 3*MAD): flagged (dark ring), never dropped; an 'excl. outliers' row is provided as extra information.

## Figures

Parity (predicted vs measured, y=x with +/-10% band):

- `parity_hybrid_c_star.png` - hybrid c_star: n=18, bias=+0.1%, median APE=2.3%, RMS=3.3%
- `parity_hybrid_chamber_pressure.png` - hybrid chamber_pressure: n=35, bias=+16.8%, median APE=13.8%, RMS=20.7%
- `parity_hybrid_isp.png` - hybrid isp: n=18, bias=+9.6%, median APE=9.1%, RMS=10.5%
- `parity_hybrid_port_diameter_final.png` - hybrid port_diameter_final: n=18, bias=-9.4%, median APE=10.1%, RMS=10.6%
- `parity_hybrid_regression_rate.png` - hybrid regression_rate: n=35, bias=-20.2%, median APE=35.1%, RMS=35.8%
- `parity_hybrid_thrust.png` - hybrid thrust: n=18, bias=+9.6%, median APE=9.1%, RMS=10.5%
- `parity_liquid_isp_vac.png` - liquid isp_vac: n=4, bias=+3.0%, median APE=2.8%, RMS=4.0%
- `parity_solid_burn_rate.png` - solid burn_rate: n=27, bias=-0.4%, median APE=0.5%, RMS=2.0%

Signed error distribution: `error_distribution.png` - one row per main cell, diamond marks the bias, dashed line marks zero.

## Author commentary

> The numbers above are auto-generated; the narrative below is maintained by the authors in `COMMENTARY.md`.

### Overall agreement

Across the three motor types HRMA tracks the measured data at the level
expected of a preliminary-design tool built on theoretical thermochemistry.
Hybrid characteristic velocity agrees with 18 static-fire measurements to a
median APE of about 2 % with essentially zero bias after the 2026-07-18
thermochemistry corrections (HTPB heat of formation moved to the CEA R-45
card value; gaseous-oxygen oxidizer path fixed). Liquid vacuum specific
impulse matches four published engine ratings (RL10, F-1, J-2, Vulcain
family) within ~3 %. Solid strand burn rates reproduce the Nakka KNDX/KNSB
dataset to below 1 % median APE, with the important caveat discussed under
Limitations: that comparison is in-sample by construction.

### Systematic biases

The remaining biases are one-directional and physically interpretable, and
we deliberately report them rather than tune them away:

- **Chamber pressure (hybrid, +17 %)**: HRMA closes the pressure loop with
  the *theoretical* equilibrium c\*. The measured combustion efficiencies in
  the GOX/paraffin campaign (0.77-0.90) are not fed back into the model —
  doing so would make the comparison circular. A positive offset of roughly
  1/eta_c\* is therefore the expected behaviour of an uncalibrated
  theoretical model, and the per-test residuals close to within a few percent
  when multiplied by the *measured* efficiency (reported for information
  only, never scored).
- **Isp and thrust (hybrid, +10 %)**: the model uses ideal nozzle thrust
  coefficients; divergence, viscous and small-throat losses are not modelled
  and the records carry no nozzle geometry that would allow a defensible
  correction. Note that the previous release reported an artificially good
  +1.8 % here — that was two errors cancelling (a c\* deficit multiplied by
  the CF excess), which the thermochemistry fix has made visible.
- **Regression rate (hybrid, -20 %)**: the aggregate hides two subsets. The
  paraffin/GOX campaign sits close to its own published law once the flux
  basis is honoured (coefficients are G_ox-based fits and are now evaluated
  as such in the validation layer). The low-flux HTPB/N2O laboratory motor
  subset is under-predicted by up to a factor of two: the single published
  a-n set (Doran 2007, validity ~10-30 g/cm^2 s) does not extend to the
  3-7 g/cm^2 s regime where radiation and small-motor effects dominate. This
  is a documented model limit; no coefficient was fitted to the validation
  data.

### Outliers and anomalies

Anomaly-flagged records are excluded from all headline statistics but kept
visible (open markers in the parity figures). They are exactly the tests the
source paper itself marks as off-nominal: nozzle failure and erosion cases,
fuel-port failures, a premature oxidizer cut, plus one record (4L-12) whose
published port diameter contradicts the paper's own mass-flux columns and
grain outer diameter — an internal inconsistency confirmed against the
primary PDF and quarantined rather than "corrected" by guesswork. The worst
main-layer chamber-pressure point is the throttling test (4Thr-1), which a
steady-state average-flow model can only represent approximately; it is
tagged off-nominal but retained. MAD-based outliers are flagged in the
tables and never dropped.

### Limitations

The database is small and uneven: 136 records, of which 76 currently score
(53 lack sufficient inputs for a blind rerun, 7 record types are not yet
supported by the v1 adapters). Liquid engines contribute only published
rating points, not test campaigns; the solid cell is a strand-burner
comparison whose coefficients derive from the same source dataset
(implementation validation, not independent prediction — the
`fit_source_records` field in `hrma/data/burn_rate_db.py` makes this
mechanically traceable); flight records are absent entirely. Delivered
combustion efficiency, nozzle losses and erosive effects are outside the
current model form and show up as the systematic biases discussed above.
Correlation-guard tests freeze the current table per cell against the
database content hash, so any silent degradation — or a suspiciously sudden
improvement, the classic symptom of measurement leaking into prediction —
fails or warns in CI.

## Detailed correlation tables

- Runner version: 1 (adapter 1)
- Records in statistics pipeline: 199 (synthetic excluded: 0)
- DB content hash: `c64e8d7b715bbc1dfffddcb9cc38989015685dfe6b5ff3b1026ec032ae1800bd`
- Status counts: insufficient_inputs=112, not_supported=7, ok=80

Signed error convention: (predicted - measured) / measured * 100. Outliers (|error - median| > 3*MAD) are flagged, never dropped.

## Main statistics (confidence: high + medium)

| Motor | Quantity | N | Bias % | Median APE % | RMS % | Min % (test) | Max % (test) | Outliers |
|---|---|---|---|---|---|---|---|---|
| hybrid | c_star | 18 | +0.1 | 2.3 | 3.3 | -5.4 (hyb-rezaei2018-htpb-n2o-t68) | +7.0 (hyb-rezaei2018-htpb-n2o-t55) | hyb-rezaei2018-htpb-n2o-t55 |
| hybrid | c_star (excl. outliers) | 17 | -0.4 | 2.1 | 2.9 | -5.4 (hyb-rezaei2018-htpb-n2o-t68) | +5.8 (hyb-rezaei2018-htpb-n2o-t48) | flagged, not dropped |
| hybrid | chamber_pressure | 35 | +16.8 | 13.8 | 20.7 | +2.0 (hyb-rezaei2018-htpb-n2o-t59) | +41.8 (hyb-karabeyoglu2003-paraffin-gox-t4thr-1) | - |
| hybrid | isp | 18 | +9.6 | 9.1 | 10.5 | -0.4 (hyb-rezaei2018-htpb-n2o-t47) | +18.0 (hyb-rezaei2018-htpb-n2o-t69) | hyb-rezaei2018-htpb-n2o-t47, hyb-rezaei2018-htpb-n2o-t69 |
| hybrid | isp (excl. outliers) | 16 | +9.7 | 9.1 | 10.2 | +4.5 (hyb-rezaei2018-htpb-n2o-t59) | +16.2 (hyb-rezaei2018-htpb-n2o-t55) | flagged, not dropped |
| hybrid | port_diameter_final | 18 | -9.4 | 10.1 | 10.6 | -16.0 (hyb-rezaei2018-htpb-n2o-t65) | -2.1 (hyb-rezaei2018-htpb-n2o-t51) | - |
| hybrid | regression_rate | 35 | -20.2 | 35.1 | 35.8 | -56.5 (hyb-rezaei2018-htpb-n2o-t69) | +25.7 (hyb-karabeyoglu2003-paraffin-gox-t4l-04) | - |
| hybrid | thrust | 18 | +9.6 | 9.1 | 10.5 | -0.4 (hyb-rezaei2018-htpb-n2o-t47) | +18.0 (hyb-rezaei2018-htpb-n2o-t69) | hyb-rezaei2018-htpb-n2o-t47, hyb-rezaei2018-htpb-n2o-t69 |
| hybrid | thrust (excl. outliers) | 16 | +9.7 | 9.1 | 10.2 | +4.6 (hyb-rezaei2018-htpb-n2o-t59) | +16.2 (hyb-rezaei2018-htpb-n2o-t55) | flagged, not dropped |
| liquid | isp_vac | 4 | +3.0 | 2.8 | 4.0 | -0.1 (liq-rs25-109pct-spec) | +6.4 (liq-j2-sa503-1968-mr55-spec) | - |
| liquid | thrust_vac | 1 | +0.7 | 0.7 | 0.7 | +0.7 (liq-rs25-109pct-spec) | +0.7 (liq-rs25-109pct-spec) | - |
| solid | burn_rate | 27 | -0.4 | 0.5 | 2.0 | -6.6 (sol-nakka1999-knsb-p09) | +2.7 (sol-nakka1999-knsb-p10) | sol-nakka1999-kndx-p05, sol-nakka1999-knsb-p06, sol-nakka1999-knsb-p07, sol-nakka1999-knsb-p09, sol-nakka1999-knsb-p10 |
| solid | burn_rate (excl. outliers) | 22 | -0.0 | 0.4 | 0.7 | -1.6 (sol-nakka1999-kndx-p11) | +1.4 (sol-nakka1999-kndx-p07) | flagged, not dropped |

## Anomaly-flagged records (excluded from statistics)

| Test | Quantity | Error % | Note |
|---|---|---|---|
| hyb-heydari2017-htpb-n2o-s4a1-1 | c_star | +4.1 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-1 | chamber_pressure | +12.2 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-1 | port_diameter_final | -10.1 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-1 | thrust | +28.6 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-2 | c_star | +17.3 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-2 | chamber_pressure | +27.9 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-2 | port_diameter_final | -7.6 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-2 | thrust | +26.9 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-3 | c_star | +23.5 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. Ön/art yanma odası konfigürasyonu diğer testlerden farklı (Tablo 3); yazarlar doğrudan karşılaştırılamayacağını belirtiyor. |
| hyb-heydari2017-htpb-n2o-s4a1-3 | chamber_pressure | +34.7 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. Ön/art yanma odası konfigürasyonu diğer testlerden farklı (Tablo 3); yazarlar doğrudan karşılaştırılamayacağını belirtiyor. |
| hyb-heydari2017-htpb-n2o-s4a1-3 | port_diameter_final | -6.2 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. Ön/art yanma odası konfigürasyonu diğer testlerden farklı (Tablo 3); yazarlar doğrudan karşılaştırılamayacağını belirtiyor. |
| hyb-heydari2017-htpb-n2o-s4a1-3 | thrust | +37.5 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. Ön/art yanma odası konfigürasyonu diğer testlerden farklı (Tablo 3); yazarlar doğrudan karşılaştırılamayacağını belirtiyor. |
| hyb-heydari2017-htpb-n2o-s4a1-4 | c_star | +9.7 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-4 | chamber_pressure | +19.2 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-4 | port_diameter_final | -8.4 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-heydari2017-htpb-n2o-s4a1-4 | thrust | +21.0 | Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1 EKSENEL hibrit modelinin kapsamı dışında — kaynağın kendi fitleri bile ayrışıyor (eksenel r=0.40*Gox^0.37, swirl r=0.14*Gox^1.40). Kayıt ana istatistiğe değil anomali katmanına girer. |
| hyb-karabeyoglu2003-paraffin-gox-t4f-1a | chamber_pressure | +28.2 | Lule erozyonu; yakma diger yonlerden iyi (Tablo 2 notu: 'Nozzle erosion/Good test'). |
| hyb-karabeyoglu2003-paraffin-gox-t4f-1a | regression_rate | +1.8 | Lule erozyonu; yakma diger yonlerden iyi (Tablo 2 notu: 'Nozzle erosion/Good test'). |
| hyb-karabeyoglu2003-paraffin-gox-t4f-2 | chamber_pressure | +338.3 | Lule arizasi (Tablo 2 notu: 'Nozzle failure'); c* verimi rapor edilmemis (Tablo 3'te '-'). |
| hyb-karabeyoglu2003-paraffin-gox-t4f-2 | regression_rate | +6.1 | Lule arizasi (Tablo 2 notu: 'Nozzle failure'); c* verimi rapor edilmemis (Tablo 3'te '-'). |
| hyb-karabeyoglu2003-paraffin-gox-t4f-4 | chamber_pressure | +27.6 | Lule erozyonu; yakma diger yonlerden iyi (Tablo 2 notu: 'Nozzle erosion/Good test'). |
| hyb-karabeyoglu2003-paraffin-gox-t4f-4 | regression_rate | +12.2 | Lule erozyonu; yakma diger yonlerden iyi (Tablo 2 notu: 'Nozzle erosion/Good test'). |
| hyb-karabeyoglu2003-paraffin-gox-t4f-5 | chamber_pressure | +30.2 | Lule erozyonu; yakma diger yonlerden iyi (Tablo 2 notu: 'Nozzle erosion/Good test'). |
| hyb-karabeyoglu2003-paraffin-gox-t4f-5 | regression_rate | +7.8 | Lule erozyonu; yakma diger yonlerden iyi (Tablo 2 notu: 'Nozzle erosion/Good test'). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-06 | chamber_pressure | +32.6 | Port yapisal arizasi (Tablo 2 notu: 'Fuel Port Failure'): kucuk port capi (~3.00 in, %84 hacimsel doluluk) ic yuzeyde catlak olusumu ve asiri regresyona yol acti (s.5-6). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-06 | regression_rate | +7.3 | Port yapisal arizasi (Tablo 2 notu: 'Fuel Port Failure'): kucuk port capi (~3.00 in, %84 hacimsel doluluk) ic yuzeyde catlak olusumu ve asiri regresyona yol acti (s.5-6). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-07 | chamber_pressure | +33.6 | Port yapisal arizasi (Tablo 2 notu: 'Fuel Port Failure'): kucuk port capi (~3.00 in, %84 hacimsel doluluk) ic yuzeyde catlak olusumu ve asiri regresyona yol acti (s.5-6). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-07 | regression_rate | -6.9 | Port yapisal arizasi (Tablo 2 notu: 'Fuel Port Failure'): kucuk port capi (~3.00 in, %84 hacimsel doluluk) ic yuzeyde catlak olusumu ve asiri regresyona yol acti (s.5-6). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-11 | chamber_pressure | +38.5 | Kontrol sistemi arizasi: GOX akisi erken kesildi; yanma suresi saglikli veri indirgemesi icin yetersiz (s.6, Tablo 2 notu: 'Control System Failure'). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-11 | regression_rate | -15.0 | Kontrol sistemi arizasi: GOX akisi erken kesildi; yanma suresi saglikli veri indirgemesi icin yetersiz (s.6, Tablo 2 notu: 'Control System Failure'). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-12 | chamber_pressure | +34.8 | Bildiri-ici tutarsizlik (2026-07-18 fizik incelemesi, PDF Tablo 2 yeniden teyit edildi): port_diameter_initial_in=4.055 bildiride boyle yaziyor AMA bildirinin kendi G sutunlariyla celisiyor — mdot_ox=2.08 kg/s + d_i=4.055 in, G_init=24.96 g/cm2s verir (bildiri 11.06; oran 2.26, diger 24 kayitta 0.91-1.05); G_avg=9.4 icin gereken d_f=9.16 in > grain OD 7.5 in (fiziksel olarak imkansiz). Tutarli tek deger d_i~6.09 in olurdu; 4.055 buyuk olasilikla 4L-08 satirindan kopyalama hatasi. Deger bildiriye sadik birakildi, kayit istatistik disina alindi (veri uydurma yasagi). |
| hyb-karabeyoglu2003-paraffin-gox-t4l-12 | regression_rate | +53.5 | Bildiri-ici tutarsizlik (2026-07-18 fizik incelemesi, PDF Tablo 2 yeniden teyit edildi): port_diameter_initial_in=4.055 bildiride boyle yaziyor AMA bildirinin kendi G sutunlariyla celisiyor — mdot_ox=2.08 kg/s + d_i=4.055 in, G_init=24.96 g/cm2s verir (bildiri 11.06; oran 2.26, diger 24 kayitta 0.91-1.05); G_avg=9.4 icin gereken d_f=9.16 in > grain OD 7.5 in (fiziksel olarak imkansiz). Tutarli tek deger d_i~6.09 in olurdu; 4.055 buyuk olasilikla 4L-08 satirindan kopyalama hatasi. Deger bildiriye sadik birakildi, kayit istatistik disina alindi (veri uydurma yasagi). |
| hyb-karabeyoglu2003-paraffin-gox-tst | chamber_pressure | +34.0 | Catlak yakit graini (Tablo 2 notu: 'Cracked fuel grain'). |
| hyb-karabeyoglu2003-paraffin-gox-tst | regression_rate | -14.3 | Catlak yakit graini (Tablo 2 notu: 'Cracked fuel grain'). |

## Not supported (v1)

- `hyb-whitmore2020-abs-gox-regfit`: record_type 'regression_correlation' v1 korelasyon kosucusunda desteklenmiyor (toplu istatistik kayitlari kayit-basina motor kosusuna eslenemez).
- `hyb-whitmore2020-abs-gox-stats13`: record_type 'campaign_statistics' v1 korelasyon kosucusunda desteklenmiyor (toplu istatistik kayitlari kayit-basina motor kosusuna eslenemez).
- `hyb-whitmore2020-abs-nytrox87-regfit`: record_type 'regression_correlation' v1 korelasyon kosucusunda desteklenmiyor (toplu istatistik kayitlari kayit-basina motor kosusuna eslenemez).
- `hyb-whitmore2020-abs-nytrox87-stats19`: record_type 'campaign_statistics' v1 korelasyon kosucusunda desteklenmiyor (toplu istatistik kayitlari kayit-basina motor kosusuna eslenemez).
- `hyb-whitmore2020-multi-regfit-literature`: record_type 'regression_correlation' v1 korelasyon kosucusunda desteklenmiyor (toplu istatistik kayitlari kayit-basina motor kosusuna eslenemez).
- `sol-nakka1999-kndx-anfit`: record_type 'regression_correlation' v1 korelasyon kosucusunda desteklenmiyor (toplu istatistik kayitlari kayit-basina motor kosusuna eslenemez).
- `sol-nakka1999-knsb-anfit`: record_type 'regression_correlation' v1 korelasyon kosucusunda desteklenmiyor (toplu istatistik kayitlari kayit-basina motor kosusuna eslenemez).

## Insufficient inputs

- `hyb-amroc1993-htpb-lox-dm01-b1`: ['burn_time', 'mdot_ox', 'port_diameter_initial']
- `hyb-amroc1993-htpb-lox-dm01-b2`: ['burn_time', 'mdot_ox', 'port_diameter_initial']
- `hyb-amroc1993-htpb-lox-dm01-b3`: ['burn_time', 'mdot_ox', 'port_diameter_initial']
- `hyb-amroc1993-htpb-lox-dm01-b4`: ['burn_time', 'mdot_ox', 'port_diameter_initial']
- `hyb-battista2019-paraffin-gox-l1`: ['port_diameter_initial', 'throat_diameter']
- `hyb-battista2019-paraffin-gox-l2`: ['port_diameter_initial', 'throat_diameter']
- `hyb-battista2019-paraffin-gox-l3`: ['port_diameter_initial', 'throat_diameter']
- `hyb-battista2019-paraffin-gox-l5`: ['port_diameter_initial', 'throat_diameter']
- `hyb-cardillo2023-paraffin-gox-1mu`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-1s`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-2mu`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-2s`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-3mu`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-3s`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-4m`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-4s`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-5m`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-5s`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-6m`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-6s`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-7m`: ['port_diameter_initial']
- `hyb-cardillo2023-paraffin-gox-8mu`: ['port_diameter_initial']
- `hyb-carmicino2013-al1-n2ogas-02kn-t13`: ['throat_diameter']
- `hyb-carmicino2013-al1-n2ogas-02kn-t14`: ['throat_diameter']
- `hyb-carmicino2013-al1-n2ogas-02kn-t15`: ['throat_diameter']
- `hyb-carmicino2013-cb-n2ogas-02kn-t07`: ['throat_diameter']
- `hyb-carmicino2013-cb-n2ogas-02kn-t08`: ['throat_diameter']
- `hyb-carmicino2013-cb-n2ogas-02kn-t09`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-t01`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-t02`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-t03`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-t04`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-t05`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-t06`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-tr1`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-tr7`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-02kn-tr8`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-1kn-rg1`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-1kn-rg2`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-1kn-t20`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-1kn-t21`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-1kn-t22`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-1kn-t26`: ['throat_diameter']
- `hyb-carmicino2013-htpb-n2ogas-1kn-t27`: ['throat_diameter']
- `hyb-carmicino2013-nal-n2ogas-02kn-t10`: ['throat_diameter']
- `hyb-carmicino2013-nal-n2ogas-02kn-t11`: ['throat_diameter']
- `hyb-carmicino2013-nal-n2ogas-02kn-t12`: ['throat_diameter']
- `hyb-hansen2012-paraffin-htpb-n2o-t2`: ['burn_time', 'mdot_ox', 'of_ratio']
- `hyb-hansen2012-paraffin-htpb-n2o-t3`: ['burn_time', 'mdot_ox', 'of_ratio']
- `hyb-hansen2012-paraffin-htpb-n2o-t4`: ['burn_time', 'mdot_ox', 'of_ratio']
- `hyb-hansen2012-paraffin-htpb-n2o-t5`: ['burn_time', 'mdot_ox', 'of_ratio']
- `hyb-heydari2017-htpb-n2o-bench0`: ['mdot_ox']
- `hyb-heydari2017-htpb-n2o-s0a1-1`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-heydari2017-htpb-n2o-s0a1-2`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-heydari2017-htpb-n2o-s0a1-3`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-heydari2017-htpb-n2o-s0a1-4`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-heydari2017-htpb-n2o-s0a1-5`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-hpdp2003-htpb-lox-250k-m1t1`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-hpdp2003-htpb-lox-250k-m2t1`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-hpdp2003-htpb-lox-250k-m2t2`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-hpdp2003-htpb-lox-250k-m2t3`: ['mdot_ox', 'port_diameter_initial', 'throat_diameter']
- `hyb-knowles2004-htpb-lox-htt-002`: ['mdot_ox', 'of_ratio', 'port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t01`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t02`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t03`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t04`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t05`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t06`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t07`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t08`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t09`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t10`: ['port_diameter_initial']
- `hyb-palacz2023-hdpe-n2o-t11`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t20`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t21`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t23`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t24`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t56`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t62`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t64`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t66`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t70`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t71`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-t72`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-ta2`: ['port_diameter_initial']
- `hyb-rezaei2018-htpb-n2o-ta3`: ['port_diameter_initial']
- `hyb-sims1998-htpb-lox-hp24-5030`: ['burn_time', 'mdot_ox', 'of_ratio', 'port_diameter_initial', 'throat_diameter']
- `hyb-wei2025-pp-n2o-t01`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-n2o-t02`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-n2o-t03`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-n2o-t04`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-n2o-t05`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-n2o-t06`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-nytrox-t01`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-nytrox-t02`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-nytrox-t03`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-nytrox-t04`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `hyb-wei2025-pp-nytrox-t05`: ['burn_time', 'mdot_ox', 'of_ratio', 'throat_diameter']
- `liq-j2-sa503-1968-mr50-spec`: ['chamber_pressure']
- `liq-merlin1d-thrust-spec`: ['chamber_pressure', 'of_ratio']
- `liq-rl10a33a-t1`: ['chamber_pressure']
- `liq-rl10a33a-t2`: ['chamber_pressure']
- `liq-rl10a33a-t3`: ['chamber_pressure']
- `liq-rl10a33a-t4`: ['chamber_pressure']
- `liq-rl10a33a-t5`: ['chamber_pressure']
- `sol-dsc-knsb-t1`: ['chamber_diameter', 'core_diameter', 'grain_length']
- `sol-dsc-knsb-t2`: ['chamber_diameter', 'core_diameter', 'grain_length']
- `sol-dsc-knsb-t3`: ['chamber_diameter', 'core_diameter', 'grain_length']
- `sol-dsc-knsb-t4`: ['chamber_diameter', 'core_diameter', 'grain_length']
- `sol-dsc-knsb-t5`: ['chamber_diameter', 'core_diameter', 'grain_length']
- `sol-dsc-knsb-t6`: ['chamber_diameter', 'core_diameter', 'grain_length']
- `sol-nakka-knsu-cstar`: ['chamber_diameter', 'core_diameter', 'grain_length']

## Engine warnings during record runs

- `hyb-karabeyoglu2003-paraffin-gox-t4f-1`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-1a`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-1b`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-1c`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-2`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-3a`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-4`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-5`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4f-5`: G_ox = 661 kg/m²·s flooding sınırına (~600-700 kg/m²·s) yakın/üstünde — Sutton & Biblarz 9. baskı, Böl. 16
- `hyb-karabeyoglu2003-paraffin-gox-t4i-01`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-01`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-03`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-04`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-04`: G_ox = 708 kg/m²·s flooding sınırına (~600-700 kg/m²·s) yakın/üstünde — Sutton & Biblarz 9. baskı, Böl. 16
- `hyb-karabeyoglu2003-paraffin-gox-t4l-05`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-06`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-06`: G_ox = 959 kg/m²·s flooding sınırına (~600-700 kg/m²·s) yakın/üstünde — Sutton & Biblarz 9. baskı, Böl. 16
- `hyb-karabeyoglu2003-paraffin-gox-t4l-07`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-07`: G_ox = 992 kg/m²·s flooding sınırına (~600-700 kg/m²·s) yakın/üstünde — Sutton & Biblarz 9. baskı, Böl. 16
- `hyb-karabeyoglu2003-paraffin-gox-t4l-08`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-09`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-10`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-11`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4l-12`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4p-01`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4p-02`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4p-03`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4p-04`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-t4thr-1`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir
- `hyb-karabeyoglu2003-paraffin-gox-tst`: Bilinmeyen/erişilemeyen oksitleyici yoğunluğu 'gox' — N2O değerine düşürüldü; enjektör boyutlandırması yaklaşık olabilir

