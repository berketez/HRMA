# HRMA — Validation Status & Known Limitations

*Last updated: 2026-07-18. This document states honestly what HRMA has been verified
against, where it is reliable, and where it is not. HRMA is a **preliminary-design
and educational tool**, not a flight-qualification tool.*

## 2026-07-18 — Correlation-driven physics review (v2.5.0)

The first full correlation run against the 136-record real-experiment database
exposed four defects; all were fixed as **literature-backed constant/physics
corrections** (never by feeding measured values back into the model):

- **critical — 'gox' oxidizer was not handled at all.** The oxidizer dispatch
  in `combustion_analysis` only knew n2o/lox/h2o2/air; gaseous-oxygen records
  ran an **oxygen-free** equilibrium (c\* ≈ 2530 m/s, non-physical). Fixed by
  adding the gox/o2 branch (O₂, ΔHf=0 at 298 K); paraffin/GOX c\* is now
  ~1822 m/s (within ~1 % of CEA). Unknown fuel/oxidizer keys now raise instead
  of silently producing garbage, and the correlation runner captures engine
  warnings per record.
- **major — HTPB heat of formation was wrong** (−125 kJ/mol "estimated"
  ≈ −2.31 MJ/kg vs the CEA R-45 card's +0.05 MJ/kg). This under-predicted T_c
  by ~300 K in the fuel-rich region the experiments actually live in
  (O/F 2.9–4.6), the root cause of the previous −6.2 % hybrid c\* bias.
  Paraffin ΔHf was also moved to the NIST n-dodecane(l) value.
- **major — solid strand burn rates used a generic default a–n for every
  propellant**, and the coefficient's origin is MPa-based while the engine
  evaluates in bar (a one-sided ×2.24 inflation; the old +83.8 % cell).
  Published Nakka KNDX/KNSB piecewise regime fits now live in a central
  `hrma/data/burn_rate_db.py` (explicit units, source, and
  `fit_source_records`) and the strand adapter uses them.
- **minor — regression-rate flux basis.** HRMA's hybrid a–n coefficients are
  G_ox-based literature fits; the validation adapter evaluated them against
  G_total, stacking a (1+1/OF)^n factor. The validation layer now runs
  `flux_mode='ox'` (the design path is unchanged).

**Honesty notes on the new table (read before quoting numbers):**

- The **hybrid isp/thrust cells got *worse* on paper (+1.8 % → +9.6 %) and this
  is correct**: the old +1.8 % was two errors cancelling (c\* deficit × ideal-CF
  excess). With c\* fixed, the ideal-CF optimism is visible. HRMA predicts
  *theoretical* performance; the residual is consistent with un-modelled nozzle
  losses and delivered efficiency (records carry no nozzle geometry to do
  better without guessing).
- The **solid burn_rate cell (0.5 % medAPE) is in-sample**: the regime
  coefficients are the source author's own least-squares fits of the same 27
  strand points. It validates data entry + the piecewise implementation, not
  independent prediction (mechanically traceable via `fit_source_records`).
- The **hybrid chamber_pressure residual (+16.8 %)** is the theoretical-c\*
  chain: measured η_c\* (0.77–0.90 in the GOX campaign) is deliberately *not*
  fed back (circularity ban). The worst main-layer test is the throttling test
  4Thr-1, run with a steady-state average-ṁ model (tagged `off_nominal`).
- The **hybrid regression_rate cell (−20.2 %, medAPE 35.1 %)** is now honest
  rather than accidentally neutral: the Karabeyoglu paraffin subset sits near
  its own published law, while the Rezaei low-flux HTPB/N₂O subset is
  under-predicted by up to ~2× — a **documented model limit** (single published
  a–n per fuel; Doran 2007 validity ≈ 10–30 g/cm²·s; radiation and small-motor
  effects dominate below that). No coefficient was tuned to fix this.
- One record (`...t4l-12`) was anomaly-flagged after the source PDF was
  re-checked: the paper's own Table 2 port diameter contradicts its own
  G columns and the grain OD (physically impossible chain). The published
  value was kept, the record quarantined — data is never "corrected" by guess.
- Guard tests (`tests/test_correlation_guards.py`) freeze this table's
  baseline per cell (×1.25 degradation gate, absolute ceilings where approved,
  over-improvement warnings against circularity) keyed to the DB content hash.

## 2026-07-16 — Leckner gas-emissivity radiation model

The chamber radiative heat-flux term no longer treats the combustion gas as
a black body. The gas emissivity is now computed from the **Leckner (1972)
H₂O/CO₂ total-emissivity correlations** (partial pressures × mean beam
length, with the pressure-overlap correction), so
q_rad = ε_gas·σ·(T_aw⁴ − T_w⁴) uses a physically realistic ε_gas well below
1 instead of the previous black-body assumption.

**Conservatism note — the direction changed.** The old black-body term
systematically *over-predicted* the radiative load (conservative for wall
heating and thermal-protection sizing). The Leckner model is more accurate
but *less* conservative on the radiation component: thermal margins that
previously hid behind the inflated radiation term should be re-checked.
Convective (Bartz) flux, which dominates at the throat, is unchanged, as is
its ±20–30 % band.

## 2026-07-12 independent formula audit

Four independent expert review passes re-derived every physics formula in the
combustion, nozzle, regression, internal-ballistics, heat-transfer, structural,
trajectory, solid, and liquid modules against primary literature (Sutton &
Biblarz 9th ed., NASA RP-1311, Bartz 1957, NASA SP-8007, MMPDS, USSA 1976) with
independent numerical re-implementation. Outcome: **all core formulas confirmed
correct** (c\* to 12 digits, Bartz viscosity constant to 0.01 %, SP-8007
knockdown exact, ISA layers exact). Defects found and **fixed** the same day:

- **critical** — liquid nozzle expansion-ratio solver was inert (a NameError
  swallowed by a bare `except` froze ε at the fsolve seed 20 for every
  altitude); replaced with the closed-form isentropic solution. Delivered Isp
  was unaffected (CEA-anchored); reported geometry/CAD was wrong.
- **major** — solid BATES model reported n segments but burned a monolithic
  grain (chamber pressure climbed 3.4× over rating); burn area now uses the
  same segment count as the reported grain design.
- **major** — solid motor reported three inconsistent expansion ratios
  (hardcoded 8 / computed 5.9 / hardcoded 40); single source now.
- **major** — empirical flame-temperature fallback was mixture-ratio-blind
  (fake Isp peaks in the fuel-rich corner when Cantera equilibrium fails);
  now scales with equivalence ratio derived from the oxygen balance.
- **major** — structural thermal model stacked two contradictory worst cases
  (hot-soak derating + full cold gradient), collapsing every hot motor to
  SF≈0.1; now evaluates the two physically consistent scenarios separately
  and reports the governing one.
- minor — thick-wall von Mises now includes the radial stress term; solid
  temperature coefficients un-dead-coded; liquid peak heat flux reported at
  the throat; trajectory load factor is now the vector |a|; regression
  fixed-point non-convergence warns instead of failing silently.

## New physics layers (2026-07-12)

| Module | Scope | Verification anchors |
|---|---|---|
| `tank_blowdown` | Self-pressurizing N₂O equilibrium two-phase blowdown (CoolProp/Span-Wagner + embedded table) | Psat(293 K)=50.5 bar vs NIST; independent CoolProp U-V flash agrees within 1 K; mass/volume conservation to machine tolerance |
| `transient_ballistics` | Time-resolved Pc(t), F(t); regulated or blowdown feed; SP-8089 ΔP stability guards; real thrust curve exported to OpenRocket `.eng` | t=0 matches design point; quasi-steady identity Pc·Cd·At = ṁ·c\* at every step; blowdown decay physical (tank cools ~19 K/10 s) |
| `six_dof_trajectory` | 6-DOF rigid body: quaternion attitude, Barrowman CN_α/CP, weathercocking, static margin, wind | Barrowman terms match hand calculation to 1e-12; apogee matches independent planar integration within 5 %; weathercocks into wind; drag-free energy conservation |

## Verification vs. Validation (AIAA G-077 / NASA-STD-7009 terminology)

- **Verification** (is the math right?): HRMA's thermochemistry is cross-checked
  against NASA CEA (via RocketCEA) and the gas-dynamics against closed-form
  Sutton & Biblarz relations. This is **code-to-code verification**.
- **Validation** (does it predict reality?): compared against published
  static-fire / flight data where available. This is partial and ongoing.

## What is verified (code-to-code, strong)

| Area | Result |
|---|---|
| Hybrid combustion c\*, Tc, Isp | 18/18 fuel×oxidizer pairs (HTPB, paraffin, PE, PMMA, ABS, PLA × N2O, LOX, H2O2) within **≤1.5 %** of NASA CEA; mean ~0.4 %. Real Cantera equilibrium, no fallback. |
| Liquid c\* | LH2/LOX, RP-1/LOX within **<2 %** of NASA CEA (SSME c\* matches to ~0.5 %). |
| Nozzle CF / isentropic flow | Matches Sutton Eq. 3-30 and CEA rocket-mode to ~0.03 %. |
| Solid APCP c\* | Within **~1.2 %** of full AP/Al/HTPB CEA composite (two-phase). |
| Sugar propellants (KNSU/sugar) | c\*≈921 m/s, Tc≈1719 K — consistent with NASA CEA + Nakka experimental (corrected 2026-06; previous values were non-physical). |
| Solid delivered Isp (APCP ref.) | 251 s vs 265 s rated literature value (−5.4 %). *Note (2026-07-12): the earlier +2.5 % agreement was an artifact of the monolithic grain model over-pressuring the chamber; the segmented model runs at rated pressure and the delivered value sits inside the 240–270 s literature band.* |
| Test suite | 1,000+ automated tests passing (pytest). |
| Export round-trips (2026-07-13) | DXF re-read via ezdxf (layers + >30-pt contour), STEP re-imported via build123d (ISO-10303), drawing PDF ≥3 pages, injector STL volume check proves orifices are drilled; fake-STL fallbacks removed (errors now raise). |

## What is validated against real data (partial)

- **Hybrid regression rate** — compared to Rezaei et al. (HTPB/N2O, *Scientia
  Iranica* 2018): HRMA within **~32 %** of the measured rate. The residual is
  dominated by batch-to-batch scatter of the empirical `a` coefficient
  (HTPB/N2O `a` varies ~2× between studies), not a code error.

## Automated correlation snapshot (real-experiment database)

The table below is produced from the git-tracked experiment database
(`hrma/data/validation_records/`) by the automated correlation runner
(`hrma/validation/correlation_runner.py`). Only the block between the
markers is machine-generated; the rest of this document remains hand-written.

<!-- AUTO-CORRELATION:BEGIN -->
*This block is auto-generated from the real-experiment correlation run — do not edit it by hand. Regenerate with `python3 -m hrma.validation.status_report`.*

- Generated: 2026-07-18 (runner v1, adapter v1)
- Experiment DB content hash: `c64e8d7b715bbc1dfffddcb9cc38989015685dfe6b5ff3b1026ec032ae1800bd`
- Records: 199 total — scored 80, insufficient inputs 112, not supported (v1) 7, runner errors 0
- Signed error convention: (predicted - measured) / measured x 100. Outliers are flagged, never dropped; anomaly-flagged records are aggregated separately.

| Motor | Quantity | Layer | N | Bias % | Median APE % | RMS % | Worst test |
|---|---|---|---|---|---|---|---|
| hybrid | c_star | main | 18 | +0.1 | 2.3 | 3.3 | hyb-rezaei2018-htpb-n2o-t55 |
| hybrid | chamber_pressure | main | 35 | +16.8 | 13.8 | 20.7 | hyb-karabeyoglu2003-paraffin-gox-t4thr-1 |
| hybrid | isp | main | 18 | +9.6 | 9.1 | 10.5 | hyb-rezaei2018-htpb-n2o-t69 |
| hybrid | port_diameter_final | main | 18 | -9.4 | 10.1 | 10.6 | hyb-rezaei2018-htpb-n2o-t65 |
| hybrid | regression_rate | main | 35 | -20.2 | 35.1 | 35.8 | hyb-rezaei2018-htpb-n2o-t69 |
| hybrid | thrust | main | 18 | +9.6 | 9.1 | 10.5 | hyb-rezaei2018-htpb-n2o-t69 |
| liquid | isp_vac | main | 4 | +3.0 | 2.8 | 4.0 | liq-j2-sa503-1968-mr55-spec |
| liquid | thrust_vac | main | 1 | +0.7 | 0.7 | 0.7 | liq-rs25-109pct-spec |
| solid | burn_rate | main | 27 | -0.4 | 0.5 | 2.0 | sol-nakka1999-knsb-p09 |
| hybrid | c_star | anomaly | 4 | +13.7 | 13.5 | 15.5 | hyb-heydari2017-htpb-n2o-s4a1-3 |
| hybrid | chamber_pressure | anomaly | 13 | +53.2 | 32.6 | 98.2 | hyb-karabeyoglu2003-paraffin-gox-t4f-2 |
| hybrid | port_diameter_final | anomaly | 4 | -8.1 | 8.0 | 8.2 | hyb-heydari2017-htpb-n2o-s4a1-1 |
| hybrid | regression_rate | anomaly | 9 | +5.8 | 7.8 | 20.1 | hyb-karabeyoglu2003-paraffin-gox-t4l-12 |
| hybrid | thrust | anomaly | 4 | +28.5 | 27.7 | 29.1 | hyb-heydari2017-htpb-n2o-s4a1-3 |
<!-- AUTO-CORRELATION:END -->

## Known limitations (do NOT design beyond these without independent check)

1. **No flight qualification.** Combustion instability, ignition transients,
   hard-start, and true delivered c\* efficiency (η_c\*) can only be determined
   by **physical static-fire testing**. HRMA narrows the design before testing;
   it does not replace the test.
2. **Hybrid regression rate uncertainty: ±20–30 %** (intrinsic to empirical
   power-law correlations and propellant batch variability).
3. **Liquid delivered Isp is idealized.** The liquid table reports CEA
   optimum-expansion Isp; real engines (F-1, Merlin) deliver ~10–18 % lower due
   to finite expansion ratio and nozzle losses. The c\* (thermochemistry) is
   sound; the delivered-Isp figures are optimistic upper bounds.
4. **Small solid motors over-predicted.** For motors below ~75 mm (e.g. Cesaroni
   G-class), delivered Isp can be ~40 % optimistic — two-phase flow, heat loss,
   and short-L\* scale effects are not modelled (large-motor efficiency assumed).
5. **Heat transfer is ±20–30 % (Bartz).** Gas-side coefficient and wall
   temperature are order-of-magnitude correct and now conservative, but true
   wall temperature / burn-through margin require thermocouple test data.
6. **Structural margins are conservative.** Thermal stress + temperature
   derating + buckling are included; a hydrostatic proof test is still required
   before firing any chamber.
7. **Deep fuel-rich hybrid regime (O/F below normal operation)** is conservative
   (Tc under-predicted) because the gri30 mechanism omits soot/condensed-carbon
   chemistry. This is outside normal operating O/F.
8. **Baseline trajectory is a planar point-mass model.** A separate 6-DOF
   rigid-body layer (2026-07-12) adds Barrowman stability, weathercocking,
   and static-margin assessment, but its aerodynamics are linear small-α
   Barrowman theory (α ≲ 15°): use it for stability screening, not for
   tumbling/large-α flight. No aeroelasticity, spin-fin interaction, or
   turbulence model.
9. **Hybrid regression coefficients are G_ox-fitted but applied to the
   Marxman total-flux closure** — a deliberate, documented choice that raises
   predicted regression ~10–18 % (the model still under-predicts the Rezaei
   HTPB/N₂O measurement by ~32 %, so the direction is corrective). Use
   `flux_mode='ox'` for literal literature comparison; a G_total re-fit is
   future work.
10. **N₂O injector two-phase flow** (updated 2026-07-13). Injector *sizing*
    now uses the two-phase Dyer NHNE model
    (`hrma/engines/injector_design.py`), which corrects the 20–40 %
    over-prediction of the single-phase SPI equation near saturation. The
    transient blowdown *time-march* still drives the orifice with a
    design-point-calibrated SPI coefficient. Cold-flow testing to anchor Cd
    is still recommended. The blowdown tank model itself is a
    thermodynamic-equilibrium model (no wall thermal mass, no vaporization
    lag): pressure decay is slightly conservative.
11. **Black powder / double-base c\* values are not independently anchored**
    (differ ~18–20 % from the single-phase Eq. 3-32 identity of their own
    (Tc, MW, γ) sets; two-phase products partially explain this). APCP and
    sugar sets are anchored; treat BP/DB as indicative only.

## Reliability envelope (honest summary)

- **Trust for preliminary design / trade studies:** grey-fuel hybrid and liquid
  performance (c\*, Tc, ideal Isp) at ±~1.5–5 %.
- **Use with calibration / independent check:** regression rate, heat load,
  structural margin, trajectory.
- **Always required before firing:** independent cross-check (CEA / RPA /
  openMotor), hydrostatic proof test, and instrumented static fire.

## Independent cross-check tools used / recommended

NASA CEA (RocketCEA), openMotor (solid), RPA Lite (liquid), Nakka SRM (sugar),
CPropep / Combustion Toolbox (equilibrium chemistry). HRMA results should be
spot-checked against at least one of these for any serious design.
