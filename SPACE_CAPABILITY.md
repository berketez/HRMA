# HRMA — Space-Class Motor Design Capability Assessment

*Assessed: 2026-07-12, following the four-pass independent formula audit and
the addition of the transient-ballistics, tank-blowdown, and 6-DOF layers.
This is an engineering judgement, argued from the verification evidence in
[VALIDATION_STATUS.md](VALIDATION_STATUS.md) — not a marketing claim.*

## Question

Can HRMA carry the **design** of a motor for a space-shot — a 100 km
(Kármán-line) class hybrid sounding vehicle — from requirements to a
manufacturable preliminary design?

## Answer

**Yes, for preliminary design — the analysis chain is now closed end-to-end.**
Requirements → thermochemistry → sizing → transient thrust curve → feed-system
coupling → thermal/structural margins → stability and trajectory → CAD/STL and
OpenRocket export, with every physics formula in that chain independently
re-derived against primary literature (2026-07-12 audit: all core formulas
confirmed; the defects the audit found were fixed the same day).

**No, for flight qualification** — as for every analysis tool. Combustion
stability, ignition, delivered c\* efficiency, and hardware integrity are
demonstrated on the test stand, not in software. HRMA narrows the design and
the test matrix; it does not replace them.

## Capability matrix for a Kármán-class hybrid (10–20 kN, ~300 kN·s)

| Discipline | Coverage | Verification anchor | Envelope |
|---|---|---|---|
| Combustion thermochemistry | Cantera equilibrium, shifting-γ, frozen/shifting Isp | c\* ≤1.5 % vs NASA CEA over 18 propellant pairs | strong |
| Motor sizing (throat, grain, chamber, L\*) | Closed-loop with Marxman G_total regression | mass conservation analytic; Rezaei static-fire within batch scatter | strong, ±20–30 % on regression |
| **Thrust–time history** | Transient Pc(t)/F(t), quasi-steady chamber | design-point identity each step | new (2026-07-12) |
| **Feed system** | Self-pressurizing N₂O blowdown (equilibrium two-phase) + regulated mode | CoolProp U-V flash within 1 K; SP-8089 ΔP stability guards | new (2026-07-12); SPI injector is single-phase |
| Nozzle | Rao/conical/bell contours, discrete losses, altitude adaptation | CF vs Sutton/CEA ~0.03 %; ε(altitude) closed-form | strong |
| Thermal | Bartz + recovery temperature + radiation, ablative/graphite materials | RS-25 throat band 40–120 kW/m²K reproduced | ±20–30 % |
| Structural | Lamé, thermal stress scenarios, MMPDS derating, SP-8007 buckling | SP-8007 knockdown exact; hydrostatic proof still mandatory | conservative |
| **Stability & flight** | 6-DOF rigid body, Barrowman CN_α/CP, weathercock, wind | Barrowman vs hand calc 1e-12; planar cross-check ±5 % | small-α linear aero |
| Vehicle integration | OpenRocket `.eng` with the *real* transient curve, STL/CAD of as-analyzed geometry | single-source geometry pipeline | strong |

## What a space-shot campaign still needs beyond HRMA

1. **Static-fire test series** — delivered c\* efficiency, ignition transient,
   combustion stability (chug/screech), nozzle erosion rates. Feed HRMA's
   η_c\* and regression coefficients back from test data after each firing.
2. **Hydrostatic proof and burst tests** of the chamber and tank (structural
   margins in HRMA are conservative but analytical).
3. **Recovery, avionics, range safety** — outside HRMA's scope entirely.
4. **Two-phase injector characterization** for N₂O (SPI assumption is
   optimistic on orifice flow; cold-flow test recommended).
5. **6-DOF with measured aero** — Barrowman is adequate for stability
   screening; a wind-tunnel or CFD-derived Cd/CN_α set tightens apogee
   prediction.

## Bottom line

A competent team can take HRMA's output — grain and nozzle drawings, tank
volume, injector plate, thrust curve, stability margins — and go directly to
hardware procurement and a static-fire campaign for a 100 km-class hybrid.
That is exactly the standard a preliminary-design tool must meet, and each
step of that chain is now covered by an automated regression suite
(166 tests) plus the documented verification anchors above. Orbital-class,
multi-stage, TVC-guided vehicles remain outside the tool's scope.
