# HRMA — Validation Status & Known Limitations

*Last updated: 2026-06. This document states honestly what HRMA has been verified
against, where it is reliable, and where it is not. HRMA is a **preliminary-design
and educational tool**, not a flight-qualification tool.*

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
| Test suite | 127 automated tests passing (pytest). |

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
8. **Trajectory is 3-DOF point-mass.** No 6-DOF stability, fin/CP-CG, or
   detailed wind profile; apogee is an estimate, not a flight prediction.

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
