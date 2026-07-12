# HRMA — Validation Status & Known Limitations

*Last updated: 2026-07-12. This document states honestly what HRMA has been verified
against, where it is reliable, and where it is not. HRMA is a **preliminary-design
and educational tool**, not a flight-qualification tool.*

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
| Test suite | 171 automated tests passing (pytest). |
| Export round-trips (2026-07-13) | DXF re-read via ezdxf (layers + >30-pt contour), STEP re-imported via build123d (ISO-10303), drawing PDF ≥3 pages, injector STL volume check proves orifices are drilled; fake-STL fallbacks removed (errors now raise). |

## What is validated against real data (partial)

- **Hybrid regression rate** — compared to Rezaei et al. (HTPB/N2O, *Scientia
  Iranica* 2018): HRMA within **~32 %** of the measured rate. The residual is
  dominated by batch-to-batch scatter of the empirical `a` coefficient
  (HTPB/N2O `a` varies ~2× between studies), not a code error.

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
10. **N₂O injector model is single-phase (SPI).** Near-saturated N₂O feed can
    flash/cavitate; SPI can over-predict orifice flow 20–40 %. A two-phase
    (Dyer/NHNE) model is future work. The blowdown tank model itself is a
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
