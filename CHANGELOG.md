# Changelog · Değişiklik günlüğü

All notable changes to HRMA are listed here, newest first. Each entry is
written twice: English first, then Turkish. The in-app **Release Notes**
window carries the full, item-by-item list for every version.

HRMA'daki kayda değer değişiklikler burada, en yenisi en üstte olacak şekilde
listelenir. Her kayıt iki dilde yazılır: önce İngilizce, sonra Türkçe.
Uygulama içindeki **Sürüm Notları** penceresi her sürümün kalem kalem tam
listesini taşır.

---

## 3.0.5 — English

*Released 2026-10-28.*

HRMA 3.0.5 is the corrections release after 3.0.0. The work prepared as
"3.0.1" ships in this release; a separate 3.0.1 was never published. It
fixes what was found after 3.0.0 by the team's test engineer, by the
measurements for the paper (20 October), by an audit of the solid and liquid
pages (22 October), by an end-to-end user test of the interface
(26 October) and by an end-to-end acceptance test of the examples, panels
and exports (27 October). The rule of this release: a number on the screen
is either right or declined with its reason, and an input outside its
accepted range is refused by name instead of being clipped or replaced.

### Inputs, refusals and help notes (all pages)

- **Every input has a help note.** The "?" next to a field opens a note in
  the interface language: what the field is and its unit, what it changes
  in the calculation (or that it is informational only), what happens when
  it is left empty, and the accepted range defined in the code. The note
  opens with the mouse, the keyboard (Enter or Space) or by touch, closes
  with Esc, and is linked to its field for screen readers. Fields without a
  note: hybrid 96, solid 83, liquid 115 → 0 in the first round; a second
  round added 118 notes and measured 0 on six pages in every state.
- **Refusals explain themselves.** A rejected calculation (HTTP 422) shows
  the server's explanation in the interface, not only an error code. The
  message names the field by its on-screen label; the machine code stays
  in the tooltip.
- **An empty field sends no hidden number.** Liquid page: 45 fields that
  sent a pre-filled number when left empty no longer do, and 26 inputs the
  solver never read are removed. Solid page: 55 hidden substitutions in the
  parameter collector are removed. Hybrid page: the hidden 1000 / 10 /
  10000 substitutions are removed. Launch Site and the three trajectory
  panels: hidden fallback numbers are removed; the request is refused by
  name or the default is declared.

### NASA CEA comparison and thermochemistry

- **No more "NASA CEA Offline / NIST WebBook Offline" badges.** The badges
  could never show a connection: the CEA check read a local table (no
  network request), and the NIST parser did not match the real NIST page.
  Both said "Offline" on every computer, and neither source supplied a
  number to the calculation. The badges and the page-load probe are removed
  from the hybrid, solid and liquid pages. Each panel now states the source
  the calculation actually uses (oxidizer: CoolProp/REFPROP; fuel: HRMA
  catalogue with the regression-law citation; thermochemistry: Cantera with
  the mechanism actually used). `/api/database-status` reports "connected /
  not connected" and "data parsed" separately; CEA has no connection status.
- **NASA CEA comparison at the end of the results, on all three pages.**
  RocketCEA (NASA CEA) is run at the design point of the run (same chamber
  pressure, O/F and expansion ratio, HRMA's own propellant definitions).
  - Hybrid: c*, T_c, γ, M, p_e, C_F and ideal vacuum Isp, HRMA ⟷ CEA ⟷
    difference, plus the delivered c* as a separate row. Example N₂O/HTPB:
    Δc* +0.02 %, ΔT_c +0.06 %. The block states that hybrid H₂O₂ is 100 %
    pure.
  - Solid: for catalogue propellants with a known composition (APCP, KNDX,
    KNSB, KNSU) the catalogue values and the ideal nozzle next to CEA at the
    motor's own pressure, with the panel's own labels and an operating-point
    row. For propellants without an exact composition the block says why
    and shows no number.
  - Liquid: CEA's ideal values next to HRMA's delivered values, with the
    efficiency that explains each difference.
  - The comparison changes no design number. It is a code verification (the
    same inputs in two codes), not a validation against test firings; the
    block says so. It is also in the PDF report and the text export.
- **Measured agreement.** A grid was run against CEA2 (RocketCEA 1.2.1) and
  the official NASA CEA v3 (3.3.4); the two references agree within
  0.001 %. Hybrid: 648 operating points, 4532 of 4536 compared rows within
  0.5 % (T_c within 0.12 %, c* within 0.04 %). Liquid: 1559 of 1559
  thermochemistry rows; the other 121 rows are the sea-level Isp of a
  separated nozzle, where HRMA shows RocketCEA's separation estimate and
  CEA has no number to compare. Solid: 119 of 224 rows before the change
  below, 221 of 224 after. No code, unit or enthalpy-of-formation error was
  found in the hybrid or liquid thermochemistry.
- **Solid thermochemistry at the motor's own chamber pressure.** T_c, c*,
  γ, M and the nozzle (optimum ε, C_F, p_e, T_e, M_e) now come from NASA
  CEA with shifting equilibrium at the motor's chamber pressure, for APCP,
  HTPB/AP/Al, KNDX, KNSB, KNSU, sugar, non-aluminised AP/HTPB (nominal
  AP85/HTPB15) and black powder (graphite card, low confidence). Before,
  every motor used the catalogue's single pressure (about 69 bar). The
  response names the source (`nasa_cea_at_pc`, `catalogue_single_pressure`
  or `user_entered`); there is no silent fallback. Published numbers change,
  for example the KNDX example T_c −1.00 %, ε +1.21 %, sea-level Isp
  −0.12 %; APCP at 40 bar sea-level Isp −0.62 %. The black-powder c* of
  945.3 m/s (20 % above CEA's ideal) is removed. The solid c* consistency
  check now compares with the theoretical c*, so a 95 % combustion
  efficiency is no longer reported as an unexplained deficit. The liquid
  static fallback table (used only if a CEA call fails) takes c*, T_c, M
  and γ from CEA2.
- **Fuel-rich hybrid thermochemistry:** the equilibrium had no condensed
  phase, so on the fuel-rich side (N₂O/HTPB below O/F ≈ 3.2) carbon that
  should form solid graphite stayed in the gas. At O/F 2 and 20 bar,
  chamber temperature, c* and vacuum Isp were 11.5 %, 6.7 % and 5.0 % below
  NASA CEA. Solid carbon C(gr) is now part of the equilibrium wherever the
  gas is carbon-supersaturated, at every nozzle station; the 29 affected
  measured points agree with CEA within 0.05 %, and states that are not
  supersaturated are unchanged. Fuel-rich designs take longer to compute;
  the c*(O/F) table behind the burn-time curves asks the equilibrium for c*
  alone, which keeps the example 1 kN design at O/F 2.5 at 1.0 s (results
  bit-identical either way). The correlation against measured hybrid
  firings shifts accordingly (hybrid Isp bias +5.4 % → +5.9 %; see
  VALIDATION_STATUS). The high-fidelity finite-rate kinetics option models
  the gas phase only; when solid carbon is present it declines with a
  stated reason and uses the engineering correlation.
- **Liquid propellant data badge:** it no longer claims "Real-time Data" for
  a cached or stored record. "Using cached data" and "Connection failed"
  texts that described a cache that was not used are replaced by what
  happened: no state-resolved value, or properties could not be loaded,
  with fields left unchanged. The "Offline store" label is now "Stored
  copy".

### Hybrid page

- **Combustion efficiency is an input.** The c* efficiency default for
  N₂O/HTPB is 0.89, the median of the 26 measured firings in HRMA's
  validation records (Heydari 2017, Tables 2 and 4-6; Scaramuzzino/Carmicino 2013, Appendix
  A1/A2). Pairs without a measured efficiency use 1.00 and the headline says
  "IDEAL c* — no c* (combustion) efficiency applied". Published numbers
  change; example 3 kN motor: c* 1596.6 → 1420.9 m/s, Isp 235.9 → 210.1 s, propellant
  12.95 → 14.54 kg; the throat is unchanged (A_t = F/(C_F·Pc)). The
  uncertainty run uses the same efficiency for its nominal (mean shift
  −7.17 % → −0.13 %), and its efficiency spread is the spread of the same
  26 records (σ 0.03 → 0.0574, truncated to 0.77–0.99).
- **Chamber wall in three zones.** The wall under the fuel grain is
  protected during the burn (case at 293.15 K, declared as an HRMA choice);
  the pre- and post-combustion chambers need a liner, which HRMA sizes
  (2.39 mm in the example). When the conditions do not hold, the earlier
  critical path is used unchanged. The structural chain uses the declared
  case temperature when the zones are protected (fatigue CRITICAL → SAFE,
  sized wall 16.85 → 4.29 mm). Example hybrid: critical warnings 43 → 7;
  the remaining nozzle critical belongs to O/F 7 (it does not occur at
  O/F ≤ 6.5). The PDF thermal section and the dock show the three zones.
- **Pintle injector rebuilt.**
  - One canonical geometry. The results table, the cross-section drawing,
    the motor summary and the PDF report now show the same holes. Before,
    one response carried three different pintles; with the fixed defaults
    the drawn tip had 437 holes of 0.10 mm and a 0.05 mm gap.
  - When left empty, the pintle diameter is sized from the flow; the fixed
    25/50 mm defaults are removed. The housing outer diameter is not sized
    unless you give it (it needs structural and packaging inputs).
  - New optional inputs: number and diameter of the tip (secondary) holes,
    annular gap, skip distance, tangential angle. A geometry that cannot
    deliver the oxidizer flow at the design pressure drop is rejected with
    the numbers.
  - Every input says which dimension it is. Secondary holes default to
    radial. The spray angle is a result, not an input.
  - The numeric sizing rules are labelled as HRMA choices; Dressler & Bauer
    (AIAA 2000-3871) does not give them.
- **Other injector types (showerhead, impinging, swirl, coaxial).**
  - The injector table and the separate injector panel now show the injector
    circuit's own geometry. Before, one response carried two injectors:
    impinging 4 × Ø1.54 mm on screen against 3 × Ø2.11 mm in the circuit;
    swirl 1 element against 7.
  - Impinging elements are like-on-like doublets with an even hole count.
    The default plan is 4 × Ø1.83 mm instead of 3 × Ø2.11 mm, with the same
    area.
  - Removed: fields with no meaning in a hybrid (fuel/oxidizer momentum
    ratio, triplet/quadlet patterns, "fuel post") and pre-filled example
    numbers. An empty field means sized by the solver, and this is declared.
  - The separate injector design panel follows the main design and fills
    itself from the circuit inputs after a calculation.
  - Velocity and L/D bands without a source are labelled "HRMA heuristic",
    not "optimal".
  - The coaxial element is solved in the injector circuit as a single-fluid
    element, so a self-pressurised N₂O plate now uses the feed-consistent
    pressure drop.
- **The end-of-burn port now reaches the chamber wall.** When no chamber
  diameter is given, the grain outer diameter is the final port diameter
  plus twice an optional residual web (default 0, declared as an
  idealisation). The old unsourced rule "chamber = 1.5 × final port" left
  72 % of the loaded fuel unburned in the default design.
  - Multi-port grains use a single-ring layout.
  - A chamber diameter you enter is kept. Its unburned-fuel fraction is
    reported, and a chamber the final ports do not fit in is rejected with
    the smallest diameter that fits.
  - This changes the default hybrid numbers: smaller chamber, shorter
    chamber, Isp −0.01 to −0.28 % (lower achieved L*), and a higher injector
    plate safety factor (the plate spans the chamber).
  - The transient solver and the blowdown curve use the same grain
    envelope. Before, they still stopped the port at 0.8 × chamber
    diameter, so the advisory blowdown curve of a 1 kN, 10 s motor ended at
    2.75 s with 3.1 kg of N₂O still in the tank (total impulse 2621 N·s);
    it now runs to oxidizer depletion at 10.15 s (8916 N·s). With four
    ports the ports stop where they meet instead of growing to 1.93 × the
    final port. Headline thrust, Isp and chamber pressure are unchanged.
- **Blowdown curve without the end-of-burn jump.** The chamber pressure ⟷
  oxidizer flow fixed-point loop diverged near the end of the burn; the root
  is now found with a bracketed (Brent) search. Example: 9.30 s /
  24 516 N·s → 10.45 s / 26 840 N·s, and the thrust falls monotonically.
- **Materials panel before the calculation.** Chamber, injector and nozzle
  materials are selected in a visible panel; the options are every material
  the engine can model (16 / 17 / 7), with the properties the calculation
  reads and their sources. An unknown material name is rejected instead of
  silently replaced.
- **Tank pressure can be set by the user.** "Tank pressure source":
  self-pressurised (N₂O saturation pressure at the tank temperature), design
  pressure drop (LOX/H₂O₂ default), or your tank pressure. Your tank
  pressure enters the injector circuit (pressure drop = tank − chamber).
  - Rejected: a tank pressure that does not exceed the chamber pressure, and
    for N₂O a tank pressure below the saturation pressure at that
    temperature. The three refusals are translated, with the numbers in the
    local decimal format.
  - In your-tank-pressure mode the tank vessel is sized at MEOP = your tank
    pressure and the slosh model uses the liquid density at that pressure
    and temperature (example N₂O at 60 bar: required wall 1.916 mm). The
    transient endpoint refuses blowdown together with this mode by name.
  - In supercharged mode the self-pressurised blowdown curve is not
    published (pressurant expansion and dissolution are not modelled).
- **Form and panels.**
  - Total impulse mode computes I = F·t_b; an impulse without thrust or
    burn time is refused by name.
  - A reopened project returns selectors it did not store to the page
    default. Switching N₂O → LOX clears the stale value and reports the band
    error; the parametric LOX run no longer fails (the oxidizer did not
    reach the motor), and the sweep includes its end point.
  - Choosing ABS or PLA filled in a fuel density of 1040 or 1250 kg/m³
    while the sourced catalogue gives 1050 and 1240 (grain 0.95 % too long
    or 0.81 % too short). The form now uses the catalogue values.
  - The transient analysis panel sent only 14 form fields, so a four-port
    design ran as a single-port motor (final port 53.7 mm instead of
    32.8 mm). After a main calculation the panel now runs the motor of that
    calculation, and the endpoint reads the residual web.
  - The thermal panel takes its gas inputs (c*, γ, M, throat, radiation)
    from the motor.
  - New help notes for O/F, IAC/FAC, N₂O viscosity and total mass flux;
    "Design O/F" label; the pressure-drop sentence follows the feed type;
    the 6-DOF panel names the motor it runs; the trajectory panel warns
    about a stale form.
  - The tank badge in regulated N₂O mode says "used".
- **Validation:** the "port exceeds chamber" critical warning is issued only
  for real burn-through. An unsourced 0.8 × chamber rule flagged every
  default design. The injector ΔP/Pc band cites Sutton & Biblarz 9th ed.
  Ch. 8 and NASA SP-194 Ch. 5-6 instead of NASA SP-8089.

### Solid page

- **Propellant selector and default propellant KNDX.** The page has an
  explicit propellant selector whose options come from the server's
  catalogue. The burn-rate preset follows the selected propellant (KNDX and
  KNSB use their own regime tables; a propellant without a law uses Custom
  with the catalogue a-n pair). A request that mixes one propellant with
  another propellant's regime table, or whose name and preset point to
  different catalogue records, is refused (`burn_rate_law_propellant_mismatch`,
  `propellant_identity_conflict`) instead of publishing a thrust curve for
  the wrong propellant. The default propellant is KNDX instead of APCP
  (the default motor now has no critical warning).
- **Thermochemistry source: "Catalogue record" or "My value".** In
  catalogue mode (the default) T_c, M, γ and c* are read-only, show the
  record's single-pressure value and are not sent; after the calculation
  each box shows the value the solver used (for example "1696.0 K … (NASA
  CEA at 40.0 bar)"). In "My value" mode the four boxes are sent and the
  run is declared `user_entered`. A rounded form value no longer moves the
  run off CEA.
- **Default geometry from one definition.** Outer diameter 100 mm, core
  48 mm (was 30 mm; port-to-throat area ratio 2.21 at the change), grain
  length 400 mm (was 500 mm; the initial mass flux of the KNDX default
  drops from 1435.9 to 1141.2 kg/m²s, below the 1400 warning limit), three
  grains. Default page motor (KNDX, BATES): average thrust 1893.43 N, peak
  2361.55 N, total impulse 5444.19 N·s, burn time 2.875 s, sea-level Isp
  124.12 s (3.0.0: APCP, 3236.30 N, 217.60 s). The tutorial-defaults motor:
  3089.80 → 1875.05 N.
- **Case and grain gates.** The case bore must be at least the grain
  diameter plus twice the liner and insulation; a case that does not fit is
  refused with the smallest diameter that fits (`grain_does_not_fit_case`).
  The old single-diameter form is accepted and declared (`case_bore`). A
  core not smaller than the grain (`core_too_large_for_grain`) and a port
  not larger than the throat (`port_smaller_than_throat`) are refused. An
  out-of-range or unreadable input is refused (`input_not_accepted`)
  instead of being answered with a built-in value. The motor outer diameter
  in the summary uses the same formula as CAD.
- **Sizing respects the port gate.** The design-point sizer and the BATES
  envelope treat port ⟷ throat as a constraint: the smallest BATES thrust
  of the envelope is 334.27 N instead of 287.50 N, and a 300 N target is
  refused by name (`warn.solid.bates_envelope_port`). A non-converged run
  keeps its diagnostics instead of being hidden behind a port refusal. The
  web-thickness band is one definition (0.1–2500 mm).
- **Uncertainty and Monte Carlo use the main design as their nominal.** The
  nominal was different from the main result (KNDX page Isp 115.77 s
  against 125.82 s; c* efficiency applied twice and the initial temperature
  lost). Now the nominal is bit-identical in all six measured cases; KNDX
  Monte Carlo success 53 % → 56 %. Monte Carlo runs on the example project.
- **Materials, grain types and inputs.**
  - Erosive coefficient and temperature coefficient: "Catalogue / My value".
    In catalogue mode no value is sent and the solver's value is shown after
    the calculation. The thermochemistry has a similar switch (below).
  - Grain count, gap and inhibitors are disabled for non-BATES grains.
    Wagon wheel: hole count, diameter and pitch circle (overlapping holes
    are refused). Finocyl: finned length fraction. Star, fin and slot
    limits and fractional counts are refused by name.
  - Nozzle (6) and case (15) material options come from the server; yield
    strength "From material" reads wall and burst checks from the same
    record. Published: aluminium, titanium and composite case wall 2.2 →
    2.0 mm; slotted default depth 25 → 20 mm (thrust 2074.9 → 2185.7 N).
  - Dry mass is the motor's dry mass (liner included, avionics excluded).
  - The help notes were written from measurements: initial temperature
    shifts the burn rate (thrust, burn time and Isp change); ambient
    temperature affects only thermal and structural results. The heat of
    combustion field is informational (no calculation reads it) and its
    unsourced 2500 default is removed.
- **Labels.** "Motor Length" is "Case Length (chamber)", next to a new
  "Total Motor Length". The throat is shown as machined and as effective
  (with Cd). "Vacuum expansion" is "Suggested vacuum nozzle ε (not this
  motor's nozzle)". The design table states the burn window (ignition to
  web burnout; mean thrust = I_t/t_b; tail-off after burnout not modelled).
  The progressive-regressive burn profile is named.
- **Solver.** The KNDX and KNSB burn-rate laws are piecewise fits that jump
  at their regime boundaries (KNDX: −1.8 % at 2.57 MPa). When the chamber
  equilibrium fell inside such a jump, the iteration oscillated and the
  example KNDX motor reported 9 of 228 steps as not converged. The solver
  now falls back to a bracketed root search; at a jump the pressure is held
  at the boundary with the burn rate that closes the mass balance, and such
  steps are counted and declared. The example now converges in every step
  (total impulse +0.018 %). Motors with a burn-rate exponent of 0.65–0.95
  reach their real root. A time step is no longer accepted on its first
  iteration with the previous step's port mass flux (KNSB example
  mass-balance residual 7.8e-5 → 2e-8).
- **Case temperature.** When the gas-side heat transfer fails or the burn
  is not solved, the case temperature is "not solved" with a named warning
  instead of silently returning the ambient temperature; the thermal margin
  and the vessel approval are then not evaluated.
- **Panels.** The thermal panel and the SAFETY tab use the case temperature
  the motor solved (example 313.6 K; the 1683.7 K bare-case critical is
  gone). Flow, vessel and connection panels use the solid propellant and
  the case material. The trajectory panel flies the solid thrust curve with
  the sea-level Isp, the nozzle exit area and the ambient pressure (BATES
  example: 422 → apogee 5677 m). Peak thrust and peak chamber pressure
  cards are shown.

### Liquid page

- **Input gates.** An input outside its band is refused by name
  (`input_not_accepted`, one band table for 49 inputs), as are fractional
  counts, an out-of-band chamber diameter and an unreadable feed pressure.
  A pressure-fed tank below the required pressure is refused
  (`pressure_fed_tank_below_required`); the required tank pressure has one
  definition (default fuel side 130.015 → 122.536 bar) and the 8 bar margin
  is a separate field. In a turbopump cycle the feed pressure is hidden and
  declared as not used; a turbopump cycle that does not close is refused
  (`turbopump_cycle_not_closed`). A pump efficiency outside its band is a
  422 refusal.
- **Form.** Help notes from the code, one density card, no stale properties
  after a fuel change, and eight chamber materials from the engine's own
  map (CuCrZr included).
- **Wall temperature: target and solved are separate.** The limit verdict
  uses only the solved wall temperature (MET / EXCEEDED / NOT_EVALUATED);
  the structural verdict uses the solved peak temperature and is withheld
  above melting. There is one coolant outlet temperature (from the march).
  The technical PDF has liquid thermal and injector sections.
- **Film cooling.** A film-cooled design has no regenerative jacket, and the
  film flow is deducted from the delivered Isp (5 % film → −1.48 %). Film
  cooling with 0 % film is refused by name.
- **Regenerative cooling model.** The fin (rib) model is used on the water
  and RP-1 path too, Dittus-Boelter carries the Sieder-Tate viscosity
  correction (NASA SP-125 Eq. 4-23), the RP-1 channel comes from the
  engine's cooling-system block (the unsourced 3.0/2.0 mm and 5 µm
  fallbacks are removed; 3 × 2 mm is an HRMA choice) and the chamber length
  enters the march. The feed budget names the jacket pressure drop (O/F
  2.6: 92.35 → 96.51 bar, same as the cycle panel).
- **Carbon deposit on the RP-1 hot wall.** The gas-side resistance of the
  carbon layer is modelled (NASA SP-125 Eq. 4-18, Fig. 4-25 and Example
  4-3) within the LOX/RP-1 envelope of NASA TP-2862 (O/F 1.77–3.32, Pc
  4.1–13.8 MPa); outside it the result is declared out of envelope and the
  numbers are unchanged; methane and hydrogen are not affected. Published
  numbers (Pc 70 bar, CuCrZr 1 mm): peak hot-wall temperature 1636 → 660 K,
  throat heat flux 35.3 → 6.6 MW/m², total heat load 2836 → 628 kW. The
  cooling panel shows the band (nominal SP-125; conservative end: a spalled
  deposit, SP-8087 §3.4.1).
- **Two-layer regenerative wall.** A regeneratively cooled chamber is a
  channelled liner (the chamber material; thickness = chamber wall
  thickness, 1 mm when empty) inside a structural closeout (default
  Inconel 718; sized by HRMA when empty). Each layer is checked on its own
  (NASA SP-125 Eq. 4-27 and 4-31 for the liner, hoop stress for the
  closeout). The single-layer comparison "CuCrZr 1 mm against a required
  8.07 mm" is gone. The manufacturing gate checks each layer. An unknown
  closeout material is refused with the accepted values.
- **RP-1 coking in two levels.** 728 K (NASA SP-8087) is the design limit
  and a critical verdict; 561 K is a warning only. Staying below 728 K does
  not mean the wall stays free of deposits. The RP-1 march uses the same
  gas property set as the main heat-transfer chain.
- **Injector.** The default is named "Unlike doublet (F-O impinging)" (the
  old "impinging" name resolves to it with an identical response), and a
  real like-on-like doublet is available. The pintle has one canonical
  geometry (33 radial holes and the annulus; the PDF table uses it). The
  separate injector panel uses the same path as the main design. The
  injector plate has a material and a Roark/ASME check.
- **Pintle chug verdict.** The verdict is computed with two atomisation
  scales (the annular gap as the declared nominal, and the radial hole
  diameter). When they disagree the verdict is "marginal" (sensitive to the
  atomisation scale) and the nominal growth rate is still shown; no
  unsourced percentage band is used (Pilch & Erdman 1987; Nicholls 1972;
  Szuch & Wenzel TN D-4564). The default pintle moves from unstable to
  marginal.
- **Results.** The altitude curve matches the cards. The "flow separates"
  message belongs to the throttle point and comes with a CFD agreement
  section. The turbopump speed choice and the specific speed Ns are on the
  card; the turbine warning names the back pressure; the flow schematic,
  feed card and a negative power margin are shown.
- **Panels.** The thermal panel stops by name when no burn time is given;
  the flow panel takes the ambient pressure and the propellant from the
  motor (422 → 200; hybrid propellants are no longer sent for a liquid
  engine); out-of-band gas fields in the panels are a named 422 instead of
  a server error.

### Charts and interface

- **Transient analysis on a time axis.** The axis runs from 0 to the later
  of the last solved instant and the burn time; the burn time is a dashed
  line with an end marker; thrust and chamber pressure are separate charts
  (they overlapped completely before). The blowdown panel follows the same
  rule.
- **Readable charts.** Minimum font sizes in the chart theme, three
  subplots for the hybrid thrust chart, separate bands for the solid
  dual-axis panels, and notes as hover text instead of rotated text. Of 68
  measured charts, 64 had a defect before and 18 after (8 of them are 3D
  scenes that cannot be measured, 6 are deliberate dimension labels). No
  published number changed.
- **Result cards no longer count up.** The cards printed intermediate
  numbers during a 700 ms animation and could stay at an intermediate value
  in a background tab (10 s later 274.4 s instead of 287.0 s). The final
  value is written at once.
- **Turkish screen.** Raw keys on the Turkish screen dropped from 166 to 78
  in the first round and from 82 to 42 in the second (the rest are formula
  symbols, the version, WebGL and a declaration code); English sentences
  from 23 to 13, then from 14 to 0. After switching the language without
  reloading, no text of the other language remains (hybrid, solid and
  liquid measured 0). Text overlaps measured 0.
- **Layout.** The top-bar title no longer overlaps the menu (2–482 px
  before, 0 in 96 measurements). The OpenRocket side tab no longer covers
  the right edge of inputs. The Design Summary no longer overflows (38 px
  → 0). Idle 3D scenes no longer redraw (solid: 1200 frames in 10 s → 0).
- **Formulas page.** The Isp expression had √γ in the denominator (C_F
  1.370 instead of 1.6445 at γ = 1.2, p_e/p_c = 0.01); it now matches
  Sutton & Biblarz Eq. 3-30. c* is defined as c* = p_c·A_t/ṁ. Sections 1.1
  and 1.2 cite Sutton's equation numbers.

### Design with AI

- **One "Design with AI" panel on the three designer pages**, usable before
  the calculation. HRMA calls no AI service: you write your design goal,
  copy the context into the assistant you use, and paste its reply back.
- The context is written in the interface language and carries the whole
  form (hybrid 81, solid 94, liquid 97 fields; before 7 / 9 / 8): label,
  value, unit, options, accepted range, source, the solver's "not used"
  declaration, server default, plus the design goal (saved with the
  project), headline numbers, warnings, withheld verdicts and the CEA
  block.
- The assistant's suggestion block (`hrma-oneri`) is treated as untrusted
  input. Only the page's own fields are accepted, with finite numbers,
  option values or true/false. Unit mismatches, out-of-range values, the
  wrong motor type or version, invalid JSON and more than 8 changes are
  refused by name, and the rationale is shown as plain text. A before/after
  table offers "Apply" and "Apply and calculate"; a continuation package
  reports what changed.

### Flight vehicle and Launch Site

- **A saved project flies the page's motor.** Flying a saved project runs
  the same calculation endpoint as the page (in the three examples the
  project vehicle is bit-identical to the vehicle of the last calculation).
  Before, the vehicle rebuilt the motor with its own fallbacks (solid
  example inert mass 4.554 kg instead of 3.090 kg).
- Hidden fallback numbers in the Launch Site and the three trajectory panels
  are removed (named refusal or declared default). A trajectory from a
  stale form is refused by name.
- The vehicle body is at least as wide as the nozzle exit (liquid example
  0.15 m body with a 189.6 mm nozzle → 0.1896 m); the body and motor
  envelope come from one function.
- The liquid trajectory panel uses the exit area and the masses of the
  motor; the solid one its own thrust curve (see the solid page).
- Launch Site: the "vehicle unstable — playback disabled" message is no
  longer erased in the same frame, the status line sits under "Fly from this
  site", disabled buttons look disabled, the dry-mass basis is a separate
  section, and the notes box no longer covers the flight summary.

### Projects and examples

- **Older projects open.** Unchanged copies of the shipped examples are
  updated once per version (a changed copy is never touched; a deleted one
  does not come back). A solid project saved before 3.0.5 whose "case
  diameter" meant the grain diameter is migrated with a named load warning,
  and the case is derived. A solid project with a typed yield strength
  keeps it in "My value" mode.
- **Project names may contain Turkish letters** (ç ğ ı İ ö ş ü and
  capitals). A refused name names the character.
- The project list says which version computed a summary ("computed with
  v3.0.0" or "computed with an older version"), shows the save date and the
  Isp basis, and keeps an unsaved last calculation separate.
- **The three examples were regenerated** with the request body the pages
  actually send, stamped 3.0.5, and their descriptions are generated from
  their inputs. Hybrid at O/F 6.0 (critical warnings 1 → 0, Isp 209.755 s);
  solid with every field the page sends (the flight vehicle equals the
  page's motor); liquid with the two-layer wall, a 1.0 mm CuCrZr liner, O/F
  2.0, 50 bar and a 30 s burn (critical warnings 4 → 0, sea-level / vacuum
  Isp 257.114 / 301.099 s).

### CAD and exports

- **The pintle is drawn as it is designed.** STEP, STL, the 3D view, the
  technical drawing and the PDF show the post, the tip and the real radial
  holes (and the drilled annulus plate when it is published). A pintle
  without a canonical geometry is refused by name; the tangential mode is
  refused by name. The liquid pintle is drawn too.
- **One nozzle source for STEP and STL.** The 3.06 % volume difference came
  from the default volume reader of the CAD kernel (+2.50 %) and the 32
  sections of the STL (−0.64 %); both are drawn from the same wall profile,
  and the check reads the volume with an adaptive integral (1 % tolerance
  unchanged).
- **Hybrid nozzle wall from one rule with the nozzle's own material.** The
  example hybrid exported nothing (five exports refused with
  `sf_wall_mismatch`); now all five return 200. Nozzle wall 7.18 →
  21.55 mm, dry mass 11.20 → 11.98 kg; 1.5·Pc and the stress concentration
  factor are declared as HRMA choices.
- The assembly and DXF nozzle come from one source; the drilled plate is
  placed the same way in STEP and STL; the two-layer liquid wall is two
  bodies with two materials in STEP and STL (the channels are declared as
  not drawn); the total length has one definition (summary = section = 3D =
  STEP); the pintle plate thickness and mass are published.
- **Manufacturing gates.** `/api/generate-complete-package` with CAD
  enabled passes the same gates, in the same order and with the same named
  refusals, as the STL package (before, a safety factor below 1, a star
  grain or a broken throat blend produced files). The safety gate also
  reads the model-validity flag of the structural block (liquid chamber,
  solid case). A tank flat head drawn with a safety factor below 1 is
  refused (Roark Table 11.2 case 10a). The tank STEP label no longer
  carries raw client text.

### Reports and verdicts

- **One structural verdict.** The design summary and the SAFETY tab read
  the same verdict function, so the examples no longer show "do not
  proceed" on one screen and a pass on another; there is no 1000 N default.
  The failure-mode list shows a consequence severity, not a verdict.
- **PDF safety section from the motor.** The shell mass uses the chamber
  length the motor published instead of an assumed L/D = 5 (hybrid example
  4.768 → 10.987 kg); without thrust the section is not evaluated instead of
  using 1000 N (solid peak thrust: restraint force 4000 → 15 561 N).
- The solid PDF has a thermochemistry section in all three report types;
  the liquid PDF thermal table shows the two-layer wall.
- Motor scene: the time-varying flame flicker and the unsourced first shock
  diamond are removed (no fake animation).

### Security and stability

- Malformed or out-of-band panel and export inputs are answered with a named
  400/422 instead of a server error (for example panel gas fields, which
  returned 500).
- A new end-to-end acceptance test (65 API nodes and 25 browser nodes)
  calculates the three examples with the request bodies the pages really
  send, and checks every panel and export.
- Nightly CI fix.

### Documentation

- README and the validation status state the measured CEA agreement
  instead of an unsupported "≤1.5 % for all pairs", say that the liquid CEA
  comparison is not an independent check, and correct the injector element
  and material counts, the test count, the uncertainty wording (a P5–P95
  spread, not a credible interval), the random seed, the STL closure claim
  and the formal-proof counts.
- The user guides (English and Turkish) describe 3.0.5. HRMA is described
  as a preliminary-design and analysis tool in the guides, the README, the
  hybrid safety warning and the PDF report; the guides no longer point the
  reader to other software (physical testing is still required) and describe
  the basis of every result: user input, a stated source or the model's own
  solution; a missing input is named, a default is reported with its source.

### Final corrections (28 October)

- **Solid grain support.** New input "Grain Support": case-bonded (default,
  results unchanged) or cartridge-loaded (cast in a mold or liner and
  inserted, NASA SP-8073). A cartridge-loaded grain carries no case-restrained
  cure-shrinkage strain; its pressure strain is computed with the case
  supporting the grain (upper bound). The solid example is cartridge-loaded:
  bore strain 2.209 % → 0.376 %, strain safety factor 0.906 → 5.32, the
  "grain strain exceeds capability" warning is gone; thrust, Isp, impulse and
  burn time are unchanged.
- **Projects keep every field.** Opening a saved project no longer clears
  fields that depend on a selector: hybrid hole diameters, element pairs,
  impingement angle, annular gap, coaxial flow fraction, fuel density and
  impulse time; liquid fuel boiling point and heat capacity; a typed
  oxidizer density and viscosity. A save → open → calculate check covers the
  three motor pages.
- **Exports.** The liquid package `.eng` no longer fails; the package and the
  `.eng` button use one builder, and the propellant and dry masses in the
  file equal the result (liquid loaded mass 297.451 → 376.099 kg, solid
  package 2.407 → 6.141 kg).
- **Hybrid injector without a plate thickness.** Plate thickness and L/D are
  not published (null) and the injector figure no longer prints "3.0 mm" or
  an L/D for them.
- **Launch Site.** The vehicle mass that includes tanks and reserve
  propellant is labelled "Flying inert mass".
- **SAFETY tab.** The risk matrix shows band names, acceptance sentences and
  axes in the interface language (no raw `risk_matrix.acceptance.*` keys).
- **Trajectory profile.** The range axis of a vertical flight no longer
  shows SI prefixes ("0.2f"); the view is centred on zero.
- **Help notes.** Three fields gain their note (hybrid "Calculate
  trajectory", hybrid manual chamber length, Launch Site time); the liquid
  fuel density is marked optional.
- **Wording.** The user guides, README and release notes describe the basis
  of every result in technical terms.
- **Feed panel.** The slosh, pressurant and water-hammer tabs start empty and
  are filled only from the motor's own result (liquid tank pressure from the
  pump NPSH sizing, 3.647 bar, instead of the chamber pressure; water hammer on
  the motor's own oxidizer line; hybrid N2O line and injector feed pressure).
  An optional field left empty uses the module default and lists it in
  `defaults_applied`; a required field left empty is refused by name. The
  liquid slosh tab uses the motor's tank slosh block (f1 identical).
- **Nozzle flow panel.** The quasi-1D solution is labelled "ideal" and the
  motor's delivered thrust, mass flow, c* and C_F are shown beside it (hybrid
  example 3000 N, 1.458 kg/s).
- **Stability panel.** No overlapping text at 1280/1440 px; verdict, scope and
  scale badges in the interface language.
- **Uncertainty.** The 3000-sample level is named "Extended" (was
  "High-Fidelity"); panel messages and help notes use neutral technical
  wording throughout.
- **Liquid liner temperature is solved.** When the regenerative station march
  does not run, the liner temperature is solved at the throat with a 1D series
  circuit (Bartz gas side, conduction, Dittus-Boelter with the Sieder-Tate
  correction and fin effect) instead of being back-computed from an assumed
  hot wall (that path could publish a negative absolute temperature). For a
  coolant without property tables the verdict is withheld with the numbers.
  The liquid example is unchanged.
- **Liquid thermal panel** uses the liner material and thickness of a two-layer
  wall (example: CuCrZr 1.0 mm, limits 773 / 1349 K instead of the Inconel
  718 values).
- **Liquid structural FEA gives a verdict.** The FEA bridge solves the
  structural outer shell with its own material and temperature; the liner is
  judged by the motor's layer model. Liquid example: verdict given, minimum
  safety factor 1.925 (before: withheld for every regenerative case). A full
  two-material thermo-elastic mesh is planned.
- **Liquid total impulse** is published (thrust × burn time; example
  750 000 N·s); the PDF table, the safety section and the OpenRocket summary
  read the same number.

### Known limitations

- Two-layer regenerative wall: low-cycle fatigue, creep, liner ⟷ closeout
  thermal mismatch, bond strength and buckling are not modelled and are
  named in the response; the throat meridional check is not repeated for
  the closeout; the preburner ladder of a staged cycle is not in the jacket
  pressure budget. CAD draws the two layers but not the cooling channels.
- The carbon-deposit resistance applies to LOX/RP-1 inside the NASA TP-2862
  envelope only; outside it the result is declared out of envelope.
- In your-tank-pressure mode, regulator lock-up and thermal excursion are
  not modelled, and the tank structural mass is not computed.
- The CEA comparison shows no number for solid propellants without an exact
  composition; the black-powder card is low confidence. The sea-level Isp
  of a separated liquid nozzle is RocketCEA's estimate and has no CEA
  counterpart.
- The pintle's tangential mode is refused in CAD.
- Coaxial (single-fluid) hybrid element: atomisation is not modelled, and no
  atomisation number is published.

## 3.0.5 — Türkçe

*Yayın tarihi: 2026-10-28.*

HRMA 3.0.5, 3.0.0'dan sonraki düzeltme sürümüdür. "3.0.1" adıyla
hazırlanan çalışma bu sürümle çıkar; ayrı bir 3.0.1 hiç yayımlanmadı. Sürüm
3.0.0'dan sonra bulunanları düzeltir: ekibin test mühendisinin bulguları,
makale ölçümleri (20 Ekim), katı ve sıvı sayfalarının denetimi (22 Ekim),
arayüzün baştan sona kullanıcı testi (26 Ekim) ve örneklerin, panellerin ve
dışa aktarımların baştan sona kabul testi (27 Ekim). Bu sürümün kuralı:
ekrandaki bir sayı ya doğrudur ya da gerekçesiyle verilmez; kabul aralığı
dışındaki bir girdi kırpılmaz ya da değiştirilmez, adıyla reddedilir.

### Girdiler, retler ve açıklamalar (bütün sayfalar)

- **Her girdinin yanında açıklama var.** Alanın yanındaki "?" arayüz
  dilinde bir not açar: alanın ne olduğu ve birimi, hesapta neyi
  değiştirdiği (ya da yalnız bilgi amaçlı olduğu), boş bırakılırsa ne
  olduğu ve kodda tanımlı kabul aralığı. Not fareyle, klavyeyle (Enter ya
  da Boşluk) ya da dokunarak açılır, Esc ile kapanır ve ekran okuyucular
  için alanına bağlıdır. Açıklamasız alan: ilk turda hibrit 96, katı 83,
  sıvı 115 → 0; ikinci tur 118 açıklama ekledi ve altı sayfada bütün
  durumlarda 0 ölçüldü.
- **Ret nedenini söyler.** Reddedilen hesap (HTTP 422) arayüzde yalnız hata
  kodunu değil sunucunun açıklamasını gösterir. İleti alanı ekrandaki
  etiketiyle anar; makine kodu ipucu balonunda kalır.
- **Boş alan gizli sayı göndermez.** Sıvı sayfası: boş bırakıldığında ön
  dolu bir sayı gönderen 45 alan artık göndermiyor; çözücünün hiç okumadığı
  26 girdi kaldırıldı. Katı sayfası: parametre toplayıcıdaki 55 gizli ikame
  kaldırıldı. Hibrit sayfası: gizli 1000 / 10 / 10000 ikameleri kaldırıldı.
  Fırlatma Sahası ve üç yörünge paneli: gizli yedek sayılar kaldırıldı;
  istek adıyla reddedilir ya da varsayılan beyan edilir.

### NASA CEA karşılaştırması ve termokimya

- **"NASA CEA Offline / NIST WebBook Offline" rozetleri kalktı.** Rozetler
  hiçbir koşulda bağlantı gösteremezdi: CEA denetimi yerel bir tabloyu
  okuyordu (ağ isteği yok), NIST ayrıştırıcısı ise NIST'in gerçek
  sayfasıyla eşleşmiyordu. İkisi de her bilgisayarda "Offline" yazıyordu ve
  hiçbiri hesaba sayı vermiyordu. Rozetler ve sayfa açılışındaki yoklama
  hibrit, katı ve sıvı sayfalarından söküldü. Her panel artık hesabın
  gerçekten kullandığı kaynağı yazar (oksitleyici: CoolProp/REFPROP; yakıt:
  HRMA kataloğu ve regresyon yasasının atfı; termokimya: Cantera ve
  gerçekten kullanılan mekanizma). `/api/database-status` "bağlandı /
  bağlanamadı" ile "veri okunabildi mi" bilgisini ayrı verir; CEA'nın
  bağlantı durumu yoktur.
- **Üç sayfada da sonuçların sonunda NASA CEA karşılaştırması.** RocketCEA
  (NASA CEA) koşumun tasarım noktasında çalıştırılır (aynı oda basıncı, O/F
  ve genişleme oranı, HRMA'nın kendi itici tanımları).
  - Hibrit: c*, T_c, γ, M, p_e, C_F ve ideal vakum Isp, HRMA ⟷ CEA ⟷ fark;
    teslim c* ayrı satırdadır. Örnek N₂O/HTPB: Δc* +%0,02, ΔT_c +%0,06.
    Blok, hibritteki H₂O₂'nin %100 saf olduğunu yazar.
  - Katı: bileşimi bilinen katalog iticilerinde (APCP, KNDX, KNSB, KNSU)
    katalog değerleri ve ideal lüle, motorun kendi basıncında CEA ile yan
    yana; satırlar panelin kendi etiketleriyle, çalışma noktası satırıyla.
    Bileşimi kesin olmayan iticilerde blok nedenini söyler, sayı göstermez.
  - Sıvı: CEA'nın ideal değerleri HRMA'nın teslim değerleriyle yan yana;
    her farkın hangi verimle açıklandığı yazar.
  - Karşılaştırma hiçbir tasarım sayısını değiştirmez. Bu bir kod
    doğrulamasıdır (aynı girdi iki kodda), test ateşlemelerine karşı
    geçerleme değildir; blok bunu yazar. PDF raporunda ve metin dışa
    aktarımında da vardır.
- **Ölçülen uyum.** CEA2 (RocketCEA 1.2.1) ve resmî NASA CEA v3 (3.3.4) ile
  bir ızgara koşuldu; iki referans birbirinden en çok %0,001 ayrışır.
  Hibrit: 648 çalışma noktası, karşılaştırılan 4536 satırın 4532'si %0,5
  içinde (T_c %0,12, c* %0,04 içinde). Sıvı: termokimya satırlarının
  1559'u da eşleşiyor; kalan 121 satır ayrılmış lülenin deniz seviyesi
  Isp'sidir: orada HRMA RocketCEA'nın ayrılma kestirimini gösterir, CEA'nın
  karşılaştırılacak sayısı yoktur. Katı: aşağıdaki değişiklikten önce 224
  satırın 119'u, sonra 221'i. Hibrit ve sıvı termokimyasında kod, birim ya
  da oluşum entalpisi hatası bulunmadı.
- **Katı termokimyası motorun kendi oda basıncında.** T_c, c*, γ, M ve lüle
  (optimum ε, C_F, p_e, T_e, M_e) artık motorun oda basıncında kayan
  dengeyle NASA CEA'dan gelir: APCP, HTPB/AP/Al, KNDX, KNSB, KNSU, şeker,
  alüminyumsuz AP/HTPB (nominal AP85/HTPB15) ve kara barut (grafit kartı,
  düşük güven). Önceden her motor kataloğun tek basıncını (yaklaşık 69 bar)
  kullanıyordu. Yanıt kaynağı adıyla yazar (`nasa_cea_at_pc`,
  `catalogue_single_pressure` ya da `user_entered`); sessiz yedek yok.
  Yayımlanan sayılar değişir; örneğin KNDX örneğinde T_c −%1,00, ε +%1,21,
  deniz seviyesi Isp −%0,12; 40 bar'da APCP deniz seviyesi Isp −%0,62. Kara
  barutun 945,3 m/s'lik c*'ı (CEA idealinin %20 üstü) kaldırıldı. Katı c*
  tutarlılık denetimi artık teorik c* ile karşılaştırır; %95 yanma verimi
  artık "açıklanamayan eksik" diye raporlanmaz. Sıvı statik yedek tablo
  (yalnız CEA çağrısı düşerse kullanılır) c*, T_c, M ve γ'yı CEA2'den alır.
- **Yakıtça zengin hibrit termokimyası:** dengede yoğun faz yoktu; yakıtça
  zengin tarafta (N₂O/HTPB'de O/F ≈ 3,2'nin altı) katı grafit olarak
  çökmesi gereken karbon gazda kalıyordu. O/F 2 ve 20 bar'da oda sıcaklığı,
  c* ve vakum Isp NASA CEA'nın %11,5, %6,7 ve %5,0 altındaydı. Katı karbon
  C(gr) artık gazın karbonca aşırı doymuş olduğu her lüle istasyonunda
  dengeye katılır; etkilenen 29 ölçüm noktası CEA ile %0,05 içinde
  uyuşuyor, aşırı doymamış durumlar değişmedi. Yakıtça zengin tasarımların
  hesabı daha uzun sürer; yanma süresi eğrilerinin arkasındaki c*(O/F)
  tablosu dengeden yalnız c* ister, bu sayede O/F 2,5'teki 1 kN örnek
  tasarım 1,0 s'de kalır (sonuçlar iki durumda da bit-aynı). Ölçülen hibrit
  ateşlemeleriyle korelasyon buna göre kaydı (hibrit Isp sapması +%5,4 →
  +%5,9; bkz. VALIDATION_STATUS). Yüksek doğruluklu sonlu hız kinetiği
  seçeneği yalnız gaz fazını modeller; katı karbon varken gerekçesini
  söyleyerek devreden çıkar ve mühendislik korelasyonunu kullanır.
- **Sıvı itici veri rozeti:** önbellek ya da saklanan kayıt için artık
  "Real-time Data" demiyor. Kullanılmayan bir önbelleği anlatan "Using
  cached data" ve "Connection failed" metinlerinin yerine ne olduğu yazılır:
  hâl çözümlü değer yok ya da özellikler alınamadı, alanlar değiştirilmedi.
  "Offline store" etiketi "Stored copy" oldu.

### Hibrit sayfası

- **Yanma verimi bir girdi.** c* veriminin N₂O/HTPB varsayılanı 0,89'dur: HRMA'nın
  doğrulama kayıtlarındaki 26 ölçülmüş ateşlemenin ortancası (Heydari 2017,
  Tablo 2 ve 4-6; Scaramuzzino/Carmicino 2013, Ek A1/A2). Ölçülmüş verimi
  olmayan çiftler 1,00 kullanır ve başlık "İDEAL c* — c* (yanma) verimi
  uygulanmadı" der. Yayımlanan sayılar değişir; 3 kN örnek motorda c* 1596,6 → 1420,9
  m/s, Isp 235,9 → 210,1 s, itici 12,95 → 14,54 kg; boğaz değişmez
  (A_t = F/(C_F·Pc)). Belirsizlik koşusu nominalinde aynı verimi kullanır
  (ortalama kayması −%7,17 → −%0,13); verim saçılımı aynı 26 kaydın
  saçılımıdır (σ 0,03 → 0,0574, 0,77-0,99 aralığında kesilir).
- **Yanma odası cidarı üç bölge.** Yakıt bloğunun altındaki cidar yanma
  boyunca korunur (kasa 293,15 K, "HRMA seçimi" olarak beyanlı); ön ve son
  yanma odası astar ister, astarı HRMA boyutlandırır (örnekte 2,39 mm).
  Koşullar sağlanmazsa eski kritik yol aynen kullanılır. Bölgeler
  korunuyorsa yapısal zincir beyanlı kasa sıcaklığını kullanır (yorulma
  KRİTİK → GÜVENLİ, boyutlandırılan cidar 16,85 → 4,29 mm). Örnek hibritte
  kritik uyarı 43 → 7; kalan lüle kritiği O/F 7'ye aittir (O/F ≤ 6,5'te
  oluşmaz). PDF ısıl bölümü ve analiz güvertesi üç bölgeyi gösterir.
- **Pintle enjektör yeniden kuruldu.**
  - Tek kanonik geometri. Sonuç tablosu, kesit çizimi, motor özeti ve PDF
    raporu artık aynı delikleri gösterir. Önceden tek yanıtta üç farklı
    pintle vardı; sabit varsayılanlarla çizilen uçta 0,10 mm'lik 437 delik
    ve 0,05 mm boşluk çıkıyordu.
  - Boş bırakılan pintle çapı akıştan boyutlandırılır; 25/50 mm sabit
    varsayılanlar kaldırıldı. Gövde dış çapı verilmedikçe boyutlandırılmaz
    (yapısal ve yerleşim girdisi ister).
  - Yeni isteğe bağlı girdiler: uç (ikincil) delik sayısı ve çapı, anülüs
    boşluğu, skip distance, teğet açı. Tasarım basınç düşümünde oksitleyici
    debisini veremeyen geometri sayılarıyla reddedilir.
  - Her girdi hangi ölçü olduğunu yazar. İkincil delikler varsayılan olarak
    radyaldir. Sprey açısı girdi değil sonuçtur.
  - Sayısal boyutlandırma kuralları "HRMA seçimi" olarak etiketlendi;
    Dressler & Bauer (AIAA 2000-3871) bunları vermiyor.
- **Diğer enjektör tipleri (duş başlığı, çarpışmalı, swirl, koaksiyel).**
  - Enjektör tablosu ve ayrı enjektör paneli artık enjektör devresinin
    kendi geometrisini gösterir. Önceden tek yanıtta iki enjektör vardı:
    çarpışmalıda ekranda 4 × Ø1,54 mm, devrede 3 × Ø2,11 mm; swirl'de 1
    eleman ⟷ 7.
  - Çarpışmalı elemanlar çift delik sayılı benzer-akışkan doublet'tir.
    Varsayılan plan, aynı alanla 3 × Ø2,11 mm yerine 4 × Ø1,83 mm.
  - Kaldırılanlar: hibritte anlamı olmayan alanlar (yakıt/oksitleyici
    momentum oranı, triplet/quadlet desenleri, "yakıt direği") ve ön dolu
    örnek sayılar. Boş alan çözücünün boyutlandırması demektir ve beyan
    edilir.
  - Ayrı enjektör tasarım paneli ana tasarımı izler; hesaptan sonra devrenin
    girdileriyle kendini doldurur.
  - Kaynaksız hız ve L/D bantları "optimal" değil "HRMA buluşsal eşiği"
    olarak etiketlendi.
  - Koaksiyel eleman enjektör devresinde tek akışkanlı eleman olarak
    çözülür; kendinden basınçlı N₂O plakası artık beslemeyle tutarlı basınç
    düşümünü kullanır.
- **Yanma sonu port artık kamara cidarına ulaşıyor.** Kamara çapı
  verilmediğinde tane dış çapı, son port çapı artı iki kat isteğe bağlı
  artık ettir (varsayılan 0, idealizasyon olarak beyanlı). Eski kaynaksız
  "kamara = 1,5 × son port" kuralı varsayılan tasarımda yüklenen yakıtın
  %72'sini yanmadan bırakıyordu.
  - Çok portlu tanede tek halka dizilimi kullanılır.
  - Girdiğiniz kamara çapı korunur. Yanmayan yakıt kesri raporlanır; son
    portların sığmadığı kamara, sığan en küçük çapla birlikte reddedilir.
  - Bu, varsayılan hibrit sayılarını değiştirir: daha küçük ve daha kısa
    kamara, Isp −%0,01…−%0,28 (gerçekleşen L* düşer), daha yüksek enjektör
    plakası emniyet katsayısı (plaka kamara çapını kaplar).
  - Geçici çözücü ve blowdown eğrisi aynı tane zarfını kullanır. Önceden
    portu hâlâ 0,8 × kamara çapında durduruyorlardı; bu yüzden 1 kN, 10
    s'lik motorun danışma blowdown eğrisi 2,75 s'de bitiyor, tankta 3,1 kg
    N₂O kalıyordu (toplam impuls 2621 N·s). Eğri artık 10,15 s'de
    oksitleyici bitimine kadar gider (8916 N·s). Dört portta portlar
    birbirine değdikleri yerde durur; eskiden son port çapının 1,93 katına
    kadar büyüyebiliyordu. Başlık itki, Isp ve kamara basıncı değişmedi.
- **Yanma sonunda sıçramayan blowdown eğrisi.** Oda basıncı ⟷ oksitleyici
  debisi sabit nokta döngüsü yanma sonuna doğru ıraksıyordu; kök artık
  parantezli (Brent) aramayla bulunur. Örnek: 9,30 s / 24 516 N·s → 10,45 s
  / 26 840 N·s; itki tekdüze iner.
- **Hesaptan önce malzeme paneli.** Yanma odası, enjektör ve nozul
  malzemeleri görünür bir panelden seçilir. Seçenekler motorun
  modelleyebildiği bütün malzemelerdir (16 / 17 / 7); hesabın okuduğu
  özellikler ve kaynakları gösterilir. Bilinmeyen malzeme adı sessizce
  değiştirilmez, reddedilir.
- **Tank basıncını kullanıcı belirleyebilir.** "Tank basıncı kaynağı":
  kendi basınçlı (tank sıcaklığında N₂O doyma basıncı), tasarım basınç
  düşümü (LOX/H₂O₂ varsayılanı) ya da sizin tank basıncınız. Girdiğiniz
  tank basıncı enjektör devresine girer (basınç düşümü = tank − oda).
  - Reddedilenler: oda basıncını aşmayan tank basıncı ve N₂O'da o
    sıcaklıktaki doyma basıncının altındaki tank basıncı. Üç ret cümlesi
    Türkçedir, sayılar yerel ondalık biçimiyle.
  - Kullanıcı tank basıncı kipinde tank kabı MEOP = sizin tank basıncınızla
    boyutlandırılır, çalkalanma modeli o basınç ve sıcaklıktaki sıvı
    yoğunluğunu kullanır (örnek: 60 bar N₂O'da gereken cidar 1,916 mm).
    Geçici analiz ucu bu kiple birlikte blowdown isteğini adıyla reddeder.
  - Takviyeli kipte kendinden basınçlı boşalma eğrisi yayımlanmaz
    (basınçlandırıcı genleşmesi ve çözünmesi modellenmiyor).
- **Form ve paneller.**
  - Toplam impuls kipi I = F·t_b hesaplar; itki ya da yanma süresi olmadan
    yalnız impuls adıyla reddedilir.
  - Yeniden açılan projede kayıtta olmayan seçiciler sayfa varsayılanına
    döner. N₂O → LOX geçişinde bayat değer silinir ve bant hatası söylenir;
    parametrik LOX koşusu artık düşmüyor (oksitleyici motora
    geçmiyordu) ve tarama bitiş noktasını da içerir.
  - ABS ya da PLA seçilince yakıt yoğunluğu 1040 ya da 1250 kg/m³
    dolduruluyordu; kaynaklı katalog 1050 ve 1240 diyor (tane %0,95 uzun ya
    da %0,81 kısa çıkıyordu). Form artık katalog değerlerini kullanır.
  - Geçici analiz paneli yalnız 14 form alanı gönderiyordu; bu yüzden 4
    portlu bir tasarım tek portlu motor olarak çözülüyordu (son port 32,8 mm
    yerine 53,7 mm). Ana hesaptan sonra panel artık o hesabın motorunu
    koşar; uç artık eti okur.
  - Isıl panel gaz girdilerini (c*, γ, M, boğaz, ışınım) motordan alır.
  - O/F, IAC/FAC, N₂O viskozitesi ve toplam kütle akısı için yeni
    açıklamalar; "Tasarım O/F'si" etiketi; basınç düşümü cümlesi besleme
    tipini izler; 6-DOF paneli koştuğu motoru adıyla yazar; yörünge paneli
    bayat form için uyarır.
  - Regüleli N₂O kipinde tank rozeti "kullanıldı" der.
- **Doğrulama:** "port kamarayı aşıyor" kritik uyarısı yalnız gerçek
  delinmede verilir; kaynaksız 0,8 × kamara kuralı her varsayılan tasarımı
  işaretliyordu. Enjektör ΔP/Pc bandı NASA SP-8089 yerine Sutton & Biblarz
  9. baskı Böl. 8 ve NASA SP-194 Böl. 5-6'yı gösterir.

### Katı sayfası

- **Yakıt seçici ve varsayılan yakıt KNDX.** Sayfada seçenekleri sunucunun
  kataloğundan gelen açık bir yakıt seçici var. Yanma hızı hazır ayarı
  seçili yakıtı izler (KNDX ve KNSB kendi rejim tablolarını kullanır; yasası
  olmayan yakıt katalog a-n çiftiyle "Özel" kullanır). Bir yakıtı başka
  yakıtın rejim tablosuyla karıştıran ya da adı ile hazır ayarı farklı
  katalog kayıtlarına inen istek, yanlış yakıtın itki eğrisini yayımlamak
  yerine reddedilir (`burn_rate_law_propellant_mismatch`,
  `propellant_identity_conflict`). Varsayılan yakıt APCP yerine KNDX'tir
  (varsayılan motor artık kritik uyarı vermiyor).
- **Termokimya kaynağı: "Katalog kaydı" ya da "Benim değerim".** Katalog
  kipinde (varsayılan) T_c, M, γ ve c* salt okurdur, kaydın tek basınçlı
  değerini gösterir ve gönderilmez; hesaptan sonra her kutunun altında
  çözücünün kullandığı değer yazar (örneğin "1696,0 K … (40,0 bar'da NASA
  CEA)"). "Benim değerim" kipinde dört kutu gönderilir ve koşu
  `user_entered` diye beyan edilir. Yuvarlanmış bir form değeri koşuyu
  artık CEA'dan düşürmez.
- **Varsayılan geometri tek tanımdan.** Dış çap 100 mm, çekirdek 48 mm
  (önce 30 mm; değişiklik anında port/boğaz alan oranı 2,21), tane boyu
  400 mm (önce 500 mm; KNDX varsayılanının ilk kütle akısı 1435,9'dan
  1141,2 kg/m²s'ye, 1400'lük uyarı sınırının altına iner), üç tane.
  Varsayılan sayfa motoru (KNDX, BATES): ortalama itki 1893,43 N, tepe 2361,55 N, toplam
  impuls 5444,19 N·s, yanma süresi 2,875 s, deniz seviyesi Isp 124,12 s
  (3.0.0: APCP, 3236,30 N, 217,60 s). Öğretici varsayılanlı motor: 3089,80
  → 1875,05 N.
- **Kasa ve tane kapıları.** Kasa iç çapı en az tane çapı artı iki kat
  astar ve yalıtım olmalı; sığmayan kasa, sığan en küçük çapla birlikte
  reddedilir (`grain_does_not_fit_case`). Eski tek çaplı biçim kabul edilir
  ve beyan edilir (`case_bore`). Taneden küçük olmayan çekirdek
  (`core_too_large_for_grain`) ve boğazdan büyük olmayan port
  (`port_smaller_than_throat`) reddedilir. Aralık dışı ya da okunamayan
  girdi, yerleşik bir değerle yanıtlanmak yerine reddedilir
  (`input_not_accepted`). Özetteki motor dış çapı CAD ile aynı formülü
  kullanır.
- **Boyutlandırma port kapısına uyar.** Tasarım noktası boyutlandırıcısı ve
  BATES zarfı port ⟷ boğaz oranını kısıt olarak taşır: zarfın en küçük BATES
  itkisi 287,50 N yerine 334,27 N'dir ve 300 N hedefi adıyla reddedilir
  (`warn.solid.bates_envelope_port`). Yakınsamayan koşu tanısını port
  reddinin arkasında kaybetmez. Et kalınlığı bandı tek tanımdır (0,1-2500
  mm).
- **Belirsizlik ve Monte Carlo ana tasarımı nominal alır.** Nominal ana
  sonuçtan farklıydı (KNDX sayfasında Isp 125,82 s yerine 115,77 s; c*
  verimi iki kez uygulanıyor, başlangıç sıcaklığı kayboluyordu). Artık
  ölçülen altı vakanın altısında nominal bit-aynı; KNDX Monte Carlo başarısı
  %53 → %56. Monte Carlo örnek projede çalışır.
- **Malzemeler, tane tipleri ve girdiler.**
  - Erozif katsayı ve sıcaklık katsayısı: "Katalog / Benim değerim".
    Katalog kipinde değer gönderilmez, hesaptan sonra çözücünün değeri
    gösterilir.
  - Tane sayısı, boşluk ve inhibitörler BATES dışı tanelerde devre dışıdır.
    Wagon wheel: delik sayısı, çapı ve bölüm dairesi (kesişen delik
    reddedilir). Finocyl: kanatlı boy oranı. Yıldız, kanat ve yarık
    sınırları ve kesirli adetler adıyla reddedilir.
  - Lüle (6) ve kasa (15) malzeme seçenekleri sunucudan gelir; akma
    dayanımı "Malzemeden" kipinde cidar ve patlama denetimlerini aynı
    kayıttan okur. Yayımlanan: alüminyum, titanyum ve kompozit kasa cidarı
    2,2 → 2,0 mm; yarıklı tanenin varsayılan derinliği 25 → 20 mm (itki
    2074,9 → 2185,7 N).
  - Kuru kütle motorun kuru kütlesidir (astar dâhil, aviyonik hariç).
  - Açıklamalar ölçülerek yazıldı: başlangıç sıcaklığı yanma hızını
    kaydırır (itki, yanma süresi ve Isp değişir); ortam sıcaklığı yalnız
    ısıl ve yapısal sonuçları etkiler. Yanma ısısı alanı bilgi amaçlıdır
    (hiçbir hesap okumaz); kaynaksız 2500 varsayılanı kaldırıldı.
- **Etiketler.** "Motor Uzunluğu" artık "Kasa Uzunluğu (oda)"dır; yanında
  yeni "Toplam Motor Uzunluğu" var. Boğaz işlenen ve etkin (Cd'li) olarak
  ayrı gösterilir. "Vakum Genleşmesi" artık "Önerilen vakum lülesi ε (bu
  motorun lülesi değil)". Tasarım tablosu yanma penceresini yazar
  (ateşlemeden et tükenişine; ortalama itki = I_t/t_b; tükeniş sonrası
  iniş modellenmez). Artan-azalan yanma profili adıyla anılır.
- **Çözücü.** KNDX ve KNSB yanma hızı yasaları rejim sınırlarında sıçrayan
  parçalı fitlerdir (KNDX: 2,57 MPa'da −%1,8). Oda dengesi böyle bir
  sıçramanın içine düşünce yineleme salınıyor ve örnek KNDX motoru 228
  adımın 9'unu yakınsamamış sayıyordu. Çözücü artık parantezli kök
  aramasına düşer; sıçramada basınç sınırda tutulur ve kütle dengesini
  kapatan yanma hızı kullanılır, bu adımlar sayılır ve beyan edilir. Örnek
  artık her adımda yakınsıyor (toplam impuls +%0,018). Yanma hızı üssü
  0,65-0,95 olan motorlar gerçek köklerine ulaşır. Bir zaman adımı artık
  ilk yinelemede önceki adımın port kütle akısıyla kabul edilmez (KNSB
  örneğinde kütle dengesi artığı 7,8e-5 → 2e-8).
- **Kasa sıcaklığı.** Gaz tarafı ısı geçişi çökerse ya da yanma çözülmemişse
  kasa sıcaklığı, sessizce ortam sıcaklığına dönmek yerine adlı bir
  uyarıyla "çözülmedi" olur; ısıl pay ve kap onayı o zaman
  değerlendirilmez.
- **Paneller.** Isıl panel ve GÜVENLİK sekmesi motorun çözdüğü kasa
  sıcaklığını kullanır (örnekte 313,6 K; 1683,7 K'lik çıplak kasa kritiği
  kalktı). Akış, kap ve bağlantı panelleri katı iticiyi ve kasa malzemesini
  kullanır. Yörünge paneli katı itki eğrisini deniz seviyesi Isp, lüle
  çıkış alanı ve ortam basıncıyla uçurur (BATES örneği: 422 → apoje
  5677 m). Tepe itki ve tepe oda basıncı kartları gösterilir.

### Sıvı sayfası

- **Girdi kapıları.** Bandı dışındaki girdi adıyla reddedilir
  (`input_not_accepted`, 49 girdi için tek bant tablosu); kesirli adet,
  bant dışı oda çapı ve okunamayan besleme basıncı da öyle. Gereken
  basıncın altındaki basınç beslemeli tank reddedilir
  (`pressure_fed_tank_below_required`); gereken tank basıncının tek tanımı
  var (varsayılan yakıt tarafı 130,015 → 122,536 bar), 8 bar pay ayrı bir
  alandır. Turbopompalı çevrimde besleme basıncı gizlenir ve kullanılmadığı
  beyan edilir; kapanmayan turbopompa çevrimi reddedilir
  (`turbopump_cycle_not_closed`). Bandı dışındaki pompa verimi 422 ile
  reddedilir.
- **Form.** Koddan yazılmış açıklamalar, tek yoğunluk kartı, yakıt
  değişince bayat özellik kalmaması ve motorun kendi eşlemesinden sekiz oda
  malzemesi (CuCrZr dâhil).
- **Cidar sıcaklığı: hedef ve çözülen ayrı.** Sınır hükmü yalnız çözülen
  cidar sıcaklığını kullanır (MET / EXCEEDED / NOT_EVALUATED); yapısal hüküm
  çözülen tepe sıcaklığı kullanır ve erime aşılırsa geri çekilir. Tek bir
  soğutucu çıkış sıcaklığı var (marştan). Teknik PDF'te sıvı ısıl ve
  enjektör bölümleri var.
- **Film soğutma.** Film soğutmalı tasarımda rejeneratif ceket yoktur;
  film debisi teslim Isp'den düşülür (%5 film → −%1,48). %0 filmle film
  soğutma adıyla reddedilir.
- **Rejeneratif soğutma modeli.** Kanat (kaburga) modeli su ve RP-1 yolunda
  da kullanılır, Dittus-Boelter Sieder-Tate viskozite düzeltmesini taşır
  (NASA SP-125 Eş. 4-23), RP-1 kanalı motorun soğutma sistemi bloğundan
  gelir (kaynaksız 3,0/2,0 mm ve 5 µm yedekleri kaldırıldı; 3 × 2 mm
  "HRMA seçimi"dir) ve oda boyu marşa girer. Besleme bütçesi ceket basınç
  düşümünü adıyla yazar (O/F 2,6: 92,35 → 96,51 bar, çevrim paneliyle
  aynı).
- **RP-1 sıcak cidarında karbon birikimi.** Karbon tabakasının gaz tarafı
  direnci, NASA TP-2862'nin LOX/RP-1 zarfı içinde (O/F 1,77-3,32, Pc
  4,1-13,8 MPa) modellenir (NASA SP-125 Eş. 4-18, Şekil 4-25 ve Örnek 4-3);
  zarf dışında sonuç zarf dışı diye beyan edilir ve sayılar değişmez; metan
  ve hidrojen etkilenmez. Yayımlanan sayılar (Pc 70 bar, CuCrZr 1 mm): tepe
  sıcak cidar sıcaklığı 1636 → 660 K, boğaz ısı akısı 35,3 → 6,6 MW/m²,
  toplam ısı yükü 2836 → 628 kW. Soğutma paneli bandı gösterir (nominal
  SP-125; tutucu uç: dökülmüş birikim, SP-8087 §3.4.1).
- **İki katmanlı rejeneratif cidar.** Rejeneratif soğutmalı oda, yapısal bir
  dış kabuğun (varsayılan Inconel 718; boşsa HRMA boyutlandırır) içinde
  kanallı bir astardır (oda malzemesi; kalınlık = oda cidar kalınlığı, boşsa
  1 mm). Her katman ayrı denetlenir (astar için NASA SP-125 Eş. 4-27 ve
  4-31, dış kabuk için çember gerilmesi). Tek katmanlı "CuCrZr 1 mm ⟷
  gereken 8,07 mm" kıyası kalktı. İmalat kapısı her katmana ayrı bakar.
  Bilinmeyen dış kabuk malzemesi kabul edilen değerlerle reddedilir.
- **RP-1 koklaşması iki kademe.** 728 K (NASA SP-8087) tasarım sınırıdır ve
  kritik hükümdür; 561 K yalnız uyarıdır. 728 K'in altında kalmak cidarın
  birikimsiz kaldığı anlamına gelmez. RP-1 marşı ana ısı geçişi zinciriyle
  aynı gaz özellik kümesini kullanır.
- **Enjektör.** Varsayılan "Unlike doublet (F-O impinging)" adını taşır
  (eski "impinging" adı ona çözülür, yanıt aynıdır) ve gerçek benzer-akışkan
  doublet seçilebilir. Pintle'ın tek kanonik geometrisi var (33 radyal
  delik ve anülüs; PDF tablosu bunu kullanır). Ayrı enjektör paneli ana
  tasarımla aynı yolu kullanır. Enjektör plakasının malzemesi ve
  Roark/ASME denetimi var.
- **Pintle chug hükmü.** Hüküm iki atomizasyon ölçeğiyle hesaplanır
  (beyanlı nominal olarak anülüs boşluğu ve radyal delik çapı). İkisi
  ayrışırsa hüküm "SINIRDA"dır (atomizasyon ölçeğine duyarlı) ve nominal
  büyüme hızı yine gösterilir; kaynaksız yüzde bandı kullanılmaz (Pilch &
  Erdman 1987; Nicholls 1972; Szuch & Wenzel TN D-4564). Varsayılan pintle
  kararsızdan sınırdaya geçer.
- **Sonuçlar.** İrtifa eğrisi kartlarla aynıdır. "Akış ayrılır" iletisi
  kısma noktasına aittir ve CFD mutabakat bölümüyle gelir. Turbopompa devir
  seçimi ve özgül hız Ns karttadır; türbin uyarısı karşı basıncı adıyla
  yazar; akış şeması, besleme kartı ve negatif güç payı gösterilir.
- **Paneller.** Isıl panel yanma süresi verilmemişse adıyla durur; akış
  paneli ortam basıncını ve iticiyi motordan alır (422 → 200; sıvı motor
  için artık hibrit iticisi gönderilmez); panellerdeki bant dışı gaz
  alanları sunucu hatası yerine adlı 422 verir.

### Grafikler ve arayüz

- **Geçici analiz zaman ekseninde.** Eksen 0'dan son çözülen an ile yanma
  süresinin büyüğüne kadar uzanır; yanma süresi kesikli çizgi ve bitiş
  işaretiyle gösterilir; itki ve oda basıncı ayrı grafiklerdir (önceden
  tamamen üst üste biniyorlardı). Blowdown paneli aynı kuralı izler.
- **Okunur grafikler.** Grafik temasında asgari yazı boyları, hibrit itki
  grafiğinde üç alt grafik, katının çift eksenli panellerinde ayrı bantlar,
  döndürülmüş yazı yerine üzerine gelince açılan notlar. Ölçülen 68
  grafikten önce 64'ünde, sonra 18'inde kusur var (8'i ölçülemeyen 3B
  sahne, 6'sı bilinçli ölçü etiketi). Yayımlanan hiçbir sayı değişmedi.
- **Sonuç kartları artık saymıyor.** Kartlar 700 ms'lik bir animasyonda ara
  sayılar basıyordu ve arka plandaki sekmede ara değerde kalabiliyordu (10
  s sonra 287,0 s yerine 274,4 s). Son değer hemen yazılır.
- **Türkçe ekran.** Türkçe ekranda ham anahtar ilk turda 166'dan 78'e,
  ikinci turda 82'den 42'ye indi (kalanlar formül simgesi, sürüm, WebGL ve
  bir beyan kodu); İngilizce cümle 23'ten 13'e, sonra 14'ten 0'a. Sayfa
  yenilenmeden dil değiştirildiğinde öteki dilin metni kalmıyor (hibrit,
  katı ve sıvıda 0 ölçüldü). Yazı çakışması 0 ölçüldü.
- **Yerleşim.** Üst şerit başlığı artık menünün üstüne binmiyor (önce 2-482
  px, 96 ölçümde 0). OpenRocket yan sekmesi artık girdilerin sağ kenarını
  örtmüyor. Tasarım Özeti artık taşmıyor (38 px → 0). Boşta duran 3B
  sahneler artık yeniden çizilmiyor (katı: 10 s'de 1200 kare → 0).
- **Formüller sayfası.** Isp ifadesinde √γ paydadaydı (γ = 1,2, p_e/p_c =
  0,01'de C_F 1,6445 yerine 1,370); artık Sutton & Biblarz Eş. 3-30 ile
  özdeş. c* tanımı c* = p_c·A_t/ṁ. Bölüm 1.1 ve 1.2 Sutton'ın denklem
  numaralarını anar.

### Yapay Zekâ ile Tasarla

- **Üç tasarım sayfasında tek "Yapay Zekâ ile Tasarla" paneli**, hesaptan
  önce de kullanılabilir. HRMA hiçbir yapay zekâ hizmetini çağırmaz: tasarım
  hedefinizi yazarsınız, bağlamı kullandığınız asistana kopyalarsınız ve
  yanıtını geri yapıştırırsınız.
- Bağlam arayüz dilinde yazılır ve formun tamamını taşır (hibrit 81, katı
  94, sıvı 97 alan; önce 7 / 9 / 8): etiket, değer, birim, seçenekler,
  kabul aralığı, kaynak, çözücünün "kullanılmadı" beyanı, sunucu varsayılanı;
  ayrıca tasarım hedefi (projeyle kaydedilir), başlık sayıları, uyarılar,
  geri çekilen hükümler ve CEA bloğu.
- Asistanın öneri bloğu (`hrma-oneri`) güvenilmez girdi sayılır. Yalnız
  sayfanın kendi alanları; sonlu sayı, seçenek değeri ya da true/false
  kabul edilir. Birim uyuşmazlığı, aralık dışı değer, yanlış motor tipi ya
  da sürüm, geçersiz JSON ve 8'den fazla değişiklik adıyla reddedilir;
  gerekçe düz metin olarak gösterilir. Önce/sonra tablosu "Uygula" ve
  "Uygula ve hesapla" sunar; devam paketi neyin değiştiğini taşır.

### Uçuş aracı ve Fırlatma Sahası

- **Kayıtlı proje sayfanın motorunu uçurur.** Kayıtlı projeyi uçurmak,
  sayfanın hesap ucunu koşar (üç örnekte proje aracı son hesabın aracıyla
  bit-aynı). Önceden araç motoru kendi yedekleriyle yeniden kuruyordu (katı
  örnekte atıl kütle 3,090 kg yerine 4,554 kg).
- Fırlatma Sahası ve üç yörünge panelindeki gizli yedek sayılar kaldırıldı
  (adlı ret ya da beyanlı varsayılan). Bayat formdan yörünge adıyla
  reddedilir.
- Araç gövdesi en az lüle çıkışı kadar geniştir (sıvı örnekte 189,6 mm
  lüleli motor için 0,15 m gövde → 0,1896 m); gövde ve motor zarfı tek
  işlevden gelir.
- Sıvı yörünge paneli motorun çıkış alanını ve kütlelerini kullanır; katı
  yörünge paneli kendi itki eğrisini (bkz. katı sayfası).
- Fırlatma Sahası: "araç kararsız — oynatma kapalı" iletisi artık aynı
  karede silinmiyor; durum satırı "Bu sahadan uçur" düğmesinin altında;
  kapalı düğmeler soluk görünür; kuru kütle dayanağı ayrı bir bölümdür; not
  kutusu artık uçuş özetini örtmüyor.

### Projeler ve örnekler

- **Eski projeler açılır.** Dağıtılan örneklerin değiştirilmemiş kopyaları
  her sürümde bir kez güncellenir (değiştirilmiş kopyaya dokunulmaz,
  silinen geri gelmez). 3.0.5 öncesinde kaydedilmiş, "kasa çapı" alanı tane
  çapı anlamına gelen katı proje adlı bir yükleme uyarısıyla göç ettirilir
  ve kasa türetilir. Akma dayanımını elle yazmış katı proje değeri "Benim
  değerim" kipinde korur.
- **Proje adında Türkçe harf kullanılabilir** (ç ğ ı İ ö ş ü ve büyükleri).
  Reddedilen ad sorunlu karakteri adıyla söyler.
- Proje listesi özetin hangi sürümle hesaplandığını söyler ("v3.0.0 ile
  hesaplandı" ya da "daha eski bir sürümle hesaplandı"), kayıt tarihini ve
  Isp tabanını gösterir, kaydedilmemiş son hesabı ayrı tutar.
- **Üç örnek yeniden üretildi:** sayfaların gerçekten gönderdiği istek
  gövdesiyle, 3.0.5 damgasıyla; açıklamaları girdilerinden üretilir.
  Hibrit O/F 6,0'da (kritik uyarı 1 → 0, Isp 209,755 s); katı, sayfanın
  gönderdiği bütün alanlarla (uçuş aracı sayfanın motoruyla aynı); sıvı iki
  katmanlı cidarla, 1,0 mm CuCrZr astar, O/F 2,0, 50 bar ve 30 s yanma
  (kritik uyarı 4 → 0, deniz seviyesi / vakum Isp 257,114 / 301,099 s).

### CAD ve dışa aktarımlar

- **Pintle tasarlandığı gibi çizilir.** STEP, STL, 3B görünüm, teknik çizim
  ve PDF direği, ucu ve gerçek radyal delikleri gösterir (yayımlanmışsa
  delikli anülüs plakasını da). Kanonik geometrisi olmayan pintle adıyla
  reddedilir; teğet kip adıyla reddedilir. Sıvı pintle de çizilir.
- **STEP ve STL için tek lüle kaynağı.** %3,06'lık hacim farkı CAD
  çekirdeğinin varsayılan hacim okuyucusundan (+%2,50) ve STL'nin 32
  kesitinden (−%0,64) geliyordu; ikisi de aynı cidar profilinden çizilir,
  denetim hacmi uyarlamalı integralle okur (%1 tolerans aynen).
- **Hibrit lüle eti tek kuraldan, lülenin kendi malzemesiyle.** Örnek
  hibritten hiçbir dosya alınamıyordu (beş dışa aktarım `sf_wall_mismatch`
  ile reddediliyordu); artık beşi de 200. Lüle eti 7,18 → 21,55 mm, kuru
  kütle 11,20 → 11,98 kg; 1,5·Pc ve gerilme yığılma katsayısı "HRMA seçimi"
  olarak beyanlı.
- Montaj ve DXF lülesi tek kaynaktan gelir; delikli plaka STEP ve STL'de
  aynı yerleşimdedir; iki katmanlı sıvı cidarı STEP ve STL'de iki
  malzemeli iki gövdedir (kanallar çizilmedi diye beyanlı); toplam boyun tek
  tanımı var (özet = kesit = 3B = STEP); pintle plaka kalınlığı ve kütlesi
  yayımlanır.
- **İmalat kapıları.** CAD açıkken `/api/generate-complete-package`, STL
  paketiyle aynı kapılardan aynı sırayla ve aynı adlı retlerle geçer
  (önceden emniyet katsayısı 1'in altında, yıldız tane ya da bozuk boğaz
  yayı dosya üretiyordu). Emniyet kapısı yapısal bloğun model geçerlilik
  bayrağını da okur (sıvı oda, katı kasa). Emniyet katsayısı 1'in altında
  çizilen düz tank kapağı reddedilir (Roark Tablo 11.2 durum 10a). Tank STEP
  etiketine istemci metni ham girmez.

### Raporlar ve hükümler

- **Tek yapısal hüküm.** Tasarım özeti ve GÜVENLİK sekmesi aynı hüküm
  işlevini okur; örnekler artık bir ekranda "ilerlemeyin", ötekinde geçti
  demiyor; 1000 N varsayılanı yok. Arıza kipleri listesi hüküm değil sonuç
  ağırlığı gösterir.
- **PDF güvenlik bölümü motordan.** Kabuk kütlesi varsayılan L/D = 5 yerine
  motorun yayımladığı oda boyunu kullanır (hibrit örnek 4,768 → 10,987 kg);
  itki yoksa bölüm 1000 N kullanmak yerine değerlendirilmez (katı tepe
  itkisi: bağlama kuvveti 4000 → 15 561 N).
- Katı PDF'in üç rapor türünde de termokimya bölümü var; sıvı PDF ısıl
  tablosu iki katmanlı cidarı gösterir.
- Motor sahnesi: zamanla titreyen alev ve kaynaksız ilk şok elması
  kaldırıldı (sahte animasyon yok).

### Güvenlik ve kararlılık

- Bozuk ya da bant dışı panel ve dışa aktarım girdileri sunucu hatası
  yerine adlı 400/422 ile yanıtlanır (örneğin önceden 500 veren panel gaz
  alanları).
- Yeni bir baştan sona kabul testi (65 API düğümü ve 25 tarayıcı düğümü),
  üç örneği sayfaların gerçekten gönderdiği istek gövdeleriyle hesaplar ve
  her paneli ve dışa aktarımı denetler.
- Gece CI düzeltmesi.

### Belgeler

- README ve doğrulama durumu, desteksiz "bütün çiftlerde ≤%1,5" yerine
  ölçülen CEA uyumunu yazıyor; sıvıda CEA karşılaştırmasının bağımsız bir
  denetim olmadığını söylüyor; enjektör eleman ve malzeme sayılarını, test
  sayısını, belirsizlik ifadesini (güven aralığı değil P5–P95 yayılımı),
  rastgele tohumu, STL kapalılık iddiasını ve biçimsel ispat sayılarını
  düzeltiyor.
- Kullanma kılavuzları (Türkçe ve İngilizce) 3.0.5'i anlatıyor. HRMA
  kılavuzlarda, README'de, hibrit güvenlik uyarısında ve PDF raporunda bir
  ön tasarım ve analiz aracı olarak tanıtılıyor; kılavuzlar okuru artık başka
  yazılıma yönlendirmiyor (fiziksel test şartı duruyor) ve her sonucun
  dayanağını anlatıyor: kullanıcı girdisi, kaynağı belirtilen veri ya da
  modelin çözümü; eksik girdi adıyla istenir, varsayılan kaynağıyla bildirilir.

### Son düzeltmeler (28 Ekim)

- **Katı tane yerleşimi.** Yeni girdi "Tane Yerleşimi": gövdeye
  yapıştırılmış (varsayılan, sonuçlar değişmez) ya da kartuş yüklü (kalıpta
  ya da astar tüpünde dökülüp gövdeye takılan, NASA SP-8073). Kartuş yüklü
  tanede gövde kürleme büzülmesini kısıtlamaz; basınç gerinimi tanenin gövdeye
  dayandığı varsayımıyla (üst sınır) hesaplanır. Katı örnek kartuş yüklü:
  port gerinimi %2,209 → %0,376, gerinim emniyet katsayısı 0,906 → 5,32,
  "tane gerinimi kapasiteyi aşıyor" uyarısı kalktı; itki, Isp, impuls ve
  yanma süresi değişmedi.
- **Projeler hiçbir alanı kaybetmiyor.** Kayıtlı proje açılınca bir seçiciye
  bağlı alanlar artık boşalmıyor: hibritte delik çapları, eleman çifti,
  çarpışma açısı, halka aralığı, eş eksenli akış oranı, yakıt yoğunluğu ve
  impuls süresi; sıvıda yakıt kaynama noktası ve ısı sığası, elle girilen
  oksitleyici yoğunluğu ve viskozitesi. Kaydet → aç → hesapla denetimi üç
  motor sayfasını kapsıyor.
- **Dışa aktarım.** Sıvı paket `.eng` artık başarısız olmuyor; paket ve `.eng`
  düğmesi tek kurucuyu kullanıyor, dosyadaki itici ve kuru kütle sonuçla aynı
  (sıvı yüklü kütle 297,451 → 376,099 kg, katı paket 2,407 → 6,141 kg).
- **Plaka kalınlığı verilmeyen hibrit enjektör.** Plaka kalınlığı ve L/D
  yayımlanmıyor (boş) ve enjektör çizimi onlar için "3.0 mm" ya da L/D
  yazmıyor.
- **Fırlatma Sahası.** Tankları ve yedek iticiyi içeren araç kütlesinin adı
  "Uçan atıl kütle".
- **GÜVENLİK sekmesi.** Risk matrisi bant adlarını, kabul cümlelerini ve
  eksenleri arayüz dilinde gösteriyor (ham `risk_matrix.acceptance.*`
  anahtarı yok).
- **Yörünge profili.** Dikey uçuşta menzil ekseni SI öneki ("0,2f")
  göstermiyor; görünüm sıfır merkezli.
- **Açıklamalar.** Üç alan açıklamasını aldı (hibrit "Yörüngeyi hesapla",
  hibrit elle oda boyu, Fırlatma Sahası zamanı); sıvı yakıt yoğunluğu
  "isteğe bağlı" diye işaretli.
- **Üslup.** Kılavuzlar, README ve sürüm notları her sonucun dayanağını
  teknik dille anlatıyor.
- **Besleme paneli.** Çalkalanma, basınçlandırıcı ve su koçu sekmeleri boş
  açılıyor ve yalnız motorun kendi sonucundan dolduruluyor (sıvıda tank basıncı
  oda basıncı yerine pompa NPSH boyutlandırmasından, 3,647 bar; su koçu motorun
  kendi oksitleyici hattında; hibritte N2O hattı ve enjektör besleme basıncı).
  Boş bırakılan isteğe bağlı alan modülün varsayılanını kullanıyor ve
  `defaults_applied` içinde listeleniyor; boş zorunlu alan adıyla reddediliyor.
  Sıvı çalkalanma sekmesi motorun tank çalkalanma bloğunu kullanıyor (f1 aynı).
- **Nozul Akışı paneli.** Yarı-1B çözüm "ideal" diye adlandırılıyor ve yanında
  motorun teslim ettiği itki, debi, c* ve C_F gösteriliyor (hibrit örnek
  3000 N, 1,458 kg/s).
- **Kararlılık paneli.** 1280/1440 px'te yazı çakışması yok; hüküm, kapsam ve
  ölçek rozetleri arayüz dilinde.
- **Belirsizlik.** 3000 örnekli düzeyin adı "Kapsamlı" (eskiden "Yüksek
  Doğruluk"); panel iletileri ve açıklamalar baştan sona tarafsız teknik dille.
- **Sıvı astar sıcaklığı çözülüyor.** Rejeneratif istasyon marşı koşmadığında
  astar sıcaklığı boğazda 1B seri devreyle çözülüyor (Bartz gaz tarafı, iletim,
  Sieder-Tate düzeltmeli Dittus-Boelter ve kanat etkisi); varsayılan sıcak
  cidardan geriye hesaplanmıyor (o yol negatif mutlak sıcaklık
  yayımlayabiliyordu). Özellik tablosu olmayan soğutucuda hüküm sayılarıyla
  geri çekiliyor. Sıvı örnek değişmedi.
- **Sıvı termal paneli** iki katmanlı cidarda astarın malzemesini ve
  kalınlığını kullanıyor (örnek: CuCrZr 1,0 mm, sınırlar Inconel 718 değerleri
  yerine 773 / 1349 K).
- **Sıvı yapısal FEA hüküm veriyor.** FEA köprüsü yapısal dış kabuğu kendi
  malzemesi ve sıcaklığıyla çözüyor; astar motorun katman modeliyle
  değerlendiriliyor. Sıvı örnek: hüküm verildi, en küçük emniyet katsayısı
  1,925 (önce bütün rejeneratif vakalarda geri çekiliyordu). Tam iki malzemeli
  termo-elastik ağ planlandı.
- **Sıvı toplam impuls** yayımlanıyor (itki × yanma süresi; örnek
  750 000 N·s); PDF tablosu, güvenlik bölümü ve OpenRocket özeti aynı sayıyı
  okuyor.

### Bilinen sınırlar

- İki katmanlı rejeneratif cidar: düşük çevrimli yorulma, sünme, astar ⟷
  dış kabuk ısıl uyumsuzluğu, bağ dayanımı ve burkulma modellenmez ve
  yanıtta adıyla yazılır; boğaz eksenel zar denetimi dış kabukta
  tekrarlanmaz; kademeli çevrimin ön yakıcı merdiveni ceket basıncı
  bütçesinde yoktur. CAD iki katmanı çizer, soğutma kanallarını çizmez.
- Karbon birikimi direnci yalnız NASA TP-2862 zarfı içindeki LOX/RP-1'e
  uygulanır; zarf dışında sonuç zarf dışı diye beyan edilir.
- Kullanıcı tank basıncı kipinde regülatör kilitlenmesi ve ısıl sapma
  modellenmez; tank yapısal kütlesi hesaplanmaz.
- CEA karşılaştırması bileşimi kesin olmayan katı iticilerde sayı
  göstermez; kara barut kartı düşük güvenlidir. Ayrılmış sıvı lülesinin
  deniz seviyesi Isp'si RocketCEA'nın kestirimidir ve CEA karşılığı yoktur.
- Pintle'ın teğet kipi CAD'de reddedilir.
- Koaksiyel (tek akışkanlı) hibrit elemanı: atomizasyon modellenmez,
  atomizasyon sayısı yayımlanmaz.

---

## 3.0.0 — English

*Released 2026-10-15.*

HRMA 3.0.0 is the first release after 2.6.26. The work that was announced
in the application as "2.6.27 (in development)" ships in this release; a
separate 2.6.27 was never published.

HRMA is a **preliminary-design tool**: requirement → engine → analysis →
revision → CAD → hand-off to detailed analysis. It is not a
flight-qualification tool. The theme of this release is that a number is
published with its validity limits, and that a verdict the model cannot
support is **withheld with its reason** instead of being shown as a pass.

### Engine physics

- **One allowable-temperature ladder for thermal safety verdicts.** The safety
  analysis and the heat-flux chart's service limit now read the same
  allowable temperature of the material as the thermal module. Measured
  effect: stainless steel 304/316 1143 → 1073 K, carbon-carbon 2273 →
  1920 K; in a margin window of 1.3 the overall risk of such a design moves
  from MEDIUM to HIGH. A wall-temperature profile without a stated source,
  or one that cannot be read, no longer receives a positive thermal verdict.
  The thermal panel names the limit that gives the verdict (for plain steel
  the 811 K structural service limit, not the 1073 K allowable temperature
  listed next to it).
- **Hybrid: N₂O liquid inlet state is an input.** Tank temperature and
  oxidiser phase enter the combustion enthalpy balance (default: saturated
  liquid at 293.15 K, CoolProp HEOS; NASA RP-1311 §4.1). On the example
  hybrid motor: chamber temperature −56.1 K, c* −1.195 %, Isp −1.175 %.
  Gas-phase oxidisers and LOX, H₂O₂, air and aluminium cases are unchanged.
- **Hybrid: tank pressure in N₂O saturation mode.** The form shows the tank
  pressure the model actually uses (the saturation pressure at the tank
  temperature) as read-only, and the API warns when a request sends a
  different value. Example hybrid: 55.0 → 50.5 bar. The tank temperature
  has one default, 293.15 K, for the injector plate and the engine alike
  (the plate used 293 K).
- **Hybrid chamber material: one default.** A request that names no chamber
  material now uses stainless steel 304, the material the form already
  showed as selected, instead of 4130 steel, and the response declares it.
  In the browser an untouched selector sent no material, so the calculation
  used 4130 while the screen showed 304. Example hybrid: minimum structural
  safety factor 0.836 → 0.232, dry mass 85.16 → 96.80 kg.
- **Hybrid injector.** The orifice-diameter band has a single definition
  (0.5–2.5 mm, Sutton; Mishra) instead of four; plans outside the canonical
  showerhead path can change. An injector plan whose clipped pressure drop
  misses the target mass flow by more than 5 % is no longer marked as
  passing (`target_flow_not_met`). The chug-ratio residual is broken down
  term by term.
- **Hybrid grain segmentation** is reported as not modelled instead of a
  segment count the solver never used.
- **Solid APCP thermochemistry from NASA CEA.** The APCP reference record
  is the CEA equilibrium set (flame temperature 3614.8 → 3399.65 K, c*
  1598.2 → 1585.4 m/s, γ 1.1338, M 27.829 kg/kmol); the Bartz heat-transfer
  correlation uses the frozen chamber γ (1.1862) from the same run. Default
  APCP motor: sea-level Isp +0.81 %, throat heat flux −2.78 %. The
  two-phase module no longer publishes "gas-only" effective properties when
  the record already contains the condensed phase (it would count it twice).
- **Solid page defaults come from the same APCP record.** On a fresh solid
  page: density 1850 → 1810 kg/m³, chamber temperature 3200 → 3399.65 K,
  γ 1.25 → 1.1338, c* 1550 → 1585.4 m/s; sea-level Isp 206.14 → 217.60 s,
  average thrust 3134.95 → 3236.30 N, propellant mass 6.611 → 6.468 kg.
  With the corrected chamber temperature a graphite nozzle now receives a
  nozzle over-temperature warning.
- **Safety analysis: propellant class from the engine's own propellant.**
  For classes without a sourced TNT equivalent (hybrid in the safety panel,
  sugar propellants such as KNDX, black powder) the TNT equivalent, blast
  distance, fragment range and evacuation distance are "not evaluated" with
  the reason, instead of a number that had no source. The API and the PDF
  report follow the same rule as the panel: a solid propellant takes its
  class from its catalogue family (composite, double base), so KNDX is no
  longer counted as composite (1.011 kg TNT, 1600 m evacuation, MEDIUM →
  not evaluated, LOW). Example hybrid in the panel: 5.435 kg TNT and 1600 m
  evacuation → not evaluated. APCP and liquid results are unchanged.
- **Safety panel: no thermal verdict from a non-physical wall temperature.**
  For an uncooled hybrid the heat module marks its equilibrium wall
  temperature as not physical; the panel no longer sends it, so the thermal
  verdict and the combined pressure-plus-thermal safety factor are withheld
  with the reason. Example hybrid: CRITICAL (combined safety factor 0.713)
  → MEDIUM, partial.
- **Structural verdicts follow the model's validity limit.** When the
  structural model is outside its validity range (for example, the solved
  wall temperature does not reach the structural analysis), approval
  verdicts are withheld and say why: end-cap "sized and verified", the
  sizing-mode approval, the analysis-deck verdict badge, and the design
  target, fatigue and buckling verdicts of the structural safety analysis.
  The numbers stay visible. In a 52-case before/after measurement 23 cases
  changed from "SAFE · VERY LOW" to "NOT EVALUATED"; no number changed and
  no failing verdict was hidden. The liquid structural card now names the
  read-back design safety-factor target and the operating hoop safety
  factor separately.
- **The analysis deck's structural panel uses the engine's own design
  target.** The deck sends the engine's design safety-factor target instead
  of the material default and names its source. Solid example: target
  4.0 → 3.0, design-target verdict SAFE · VERY LOW → ACCEPTABLE · LOW;
  liquid example: 3.0 → 2.5, ACCEPTABLE · LOW → MARGINAL · MEDIUM.
- **Structural FEA load model.** `/api/fea/structural` loads the convergent
  and divergent sections with the 1D isentropic static pressure (γ from the
  engine result; constant chamber pressure as a declared fallback), applies
  the closed-end force and checks the force balance on every run (tolerance
  1e-3 of the end force; otherwise the verdict is withheld). The response
  states the scope: pressure loads only, no thermal stress and no
  temperature-dependent strength. Example motors, minimum safety factor:
  liquid 2.23 → 3.63 (with the wall HRMA now sizes, below), hybrid 5.53 →
  9.22, solid 1.03 → 2.19; all three verdicts, previously withheld as
  sensitive to the support location, are now given.
- **Liquid chamber wall sized by HRMA.** The liquid page no longer pre-fills
  an unsourced 5 mm wall; the engine sizes it (example: 2 mm).
- **Regenerative cooling: one temperature limit.** The cooling verdict's
  service limit is the material's allowable temperature, as in the thermal
  module, instead of its melting point (copper 1358 → 723 K, Inconel 718
  1533 → 977 K); a wall between the allowable and the melting temperature
  is now UNSAFE instead of WARNING. Peak wall temperatures, heat loads and
  pressure drops are unchanged.
- **Regenerative cooling inputs come from the engine.** The cooling panel no
  longer pre-fills unsourced values (80 channels, channel width and depth,
  liner thickness, water coolant, inlet temperature and pressure): each
  field takes the engine's published value or stays empty and required, and
  no request is sent while a required field is empty. `/api/regen-cooling`
  answers a request without `n_channels` with a named 400. When the coolant
  station march cannot run, a warning says so instead of the thermal
  verdict disappearing silently.
- **Supercritical hydrogen cooling.** Channel sizing and the published
  coolant velocity use the same hydrogen density; before, the sizing used a
  liquid density and the published velocity was about four times the
  target the sizing assumed it met. The velocity target itself is listed
  under Known limitations.
- **Liquid page fuel density.** Changing the fuel no longer sends another
  fuel's density as input (for example RP-1's 810 kg/m³ for LH2); a value
  typed by hand is kept, with a warning when the selected fuel differs. On
  a pressure-fed cycle, turbopump efficiency and gas-generator temperature
  are listed as unused inputs.

### CAD

- **CAD is drawn from the analysis geometry (single source).** An
  independent CAD check had found places where the exporter drew its own
  rule instead of the analysed engine (a star grain drawn as a plain tube,
  propellant volume +23.3 %; hybrid nozzle wall 3 mm in STEP but 7.19 mm in
  STL; tank volume 1.23×). These are fixed.
- **Fail-closed manufacturing export.** Every manufacturing export (STEP,
  DXF, drawing PDF, STL package, single STL, complete package,
  `/api/export-cad`) is refused by the server with the same named reasons
  when the structural safety factor is below 1 or the structural model is
  outside its validity range (example hybrid: drawing PDF, STL package and
  `/api/export-cad` 200 → 422). Star and finocyl grains, which the CAD
  kernel cannot yet draw faithfully, are refused with a reason instead of
  being exported as a circular port.
- **One nozzle-contour check for every export.** A contour that turns back,
  a throat radius of curvature that is not positive or cannot be read, or a
  contour angle that cannot be read gets a named 422 instead of a file built
  on a silent default (for angles 30°, 8° or 15°); a malformed contour
  block that caused a server error gets 422 too. The solid and liquid CAD
  packages draw the nozzle contour the engine published, and the DXF class
  table is written in a fixed order (same file on every run apart from
  timestamps).
- **Tank model** is a declared flat-ended cylinder; part names carry their
  source.
- **Smooth nozzle surfaces.** The nozzle in STEP is one B-spline surface of
  revolution through the same contour points instead of about a hundred
  conical facets. Lengths and end diameters are bit-identical; the throat
  differs by less than 1e-7 mm. A malformed contour returns a named 422
  error instead of a server error. The package README notes that a CAD
  tool's default volume of these surfaces can be off by 0.04–1.5 %, and
  that HRMA's nozzle mass is not read from the file.

### Launch-site map

- **Detailed offline map** (about 13 MB of bundled assets): vector borders
  with level of detail, and city and country labels that appear as you zoom
  in. Labels stay readable over snow and ice, and their count is capped
  when the whole globe is shown.
- **Bundled Earth imagery.** A packaged NASA Blue Marble texture (December
  2004, about 2 km per pixel at the equator, 1,073 tiles, 15.9 MB) is drawn
  without any network request; online tiles are requested only for finer
  detail and only when the switch below is on. The map note gives the
  measured offset between the vector coastline and the imagery (Kennedy
  coast against a NASA GIBS tile: median 598 m, 90th percentile 1.3 km).
- **Place names** follow Türkiye's official usage for a short, listed set
  of names (for example *Türkiye*, *Greek Cypriot Administration of
  Southern Cyprus*, *Khankendi*); Crimea is shown as part of Ukraine. Every
  other name is unchanged from Natural Earth 5.1.2, and the corrections are
  recorded in the map's provenance.
- **Privacy switch for satellite imagery.** Downloading imagery tiles is
  **off by default**. Until you turn it on, the server makes no outside
  request; tiles already in the local cache are still shown.

### Security

- Local API origin gates tightened: a page on another local port can no
  longer trigger the side-effecting GET endpoints, and an Origin without a
  port is checked against the server's real port.
- Request bodies: one 32 MiB limit for every endpoint, enforced by the web
  server before the body is buffered (oversized requests get a JSON 413);
  per-request item limits for configuration and composition lists; at most
  100 simultaneous connections.
- Content-Security-Policy adds `object-src 'none'` and `base-uri 'none'`.
  Server and error text is escaped before it reaches the page.
- Upload screens (STEP, OpenRocket `.ork`, motor file, CSV) check the size
  limit before sending the file; the limit is read from the server. The
  validation panel's re-compare checks it too, and an oversized request
  (413) is shown as a readable message.
- An automated API fuzzing run (3,090 requests over 104 endpoint methods)
  went from 456 findings to 0: malformed input now gets 400/422 with a
  reason instead of a server error.
- Export endpoints no longer crash on a malformed nested block. When a
  nested block of the export payload (for example `design_summary`,
  `structural_analysis`, `heat_transfer_analysis.wall_analysis`,
  `grain_design`) arrived as text or a list instead of an object, nine
  export endpoints returned HTTP 500 (measured: 108 of 10,720 requests).
  They now return 422 `invalid_export_geometry` naming the full field
  path; an unreadable `nozzle_angles` block gets the nozzle contour gate's
  refusal. The STL package endpoint returns the assembly generator's named
  refusal (422, as `/api/export-cad` does) instead of a 500 when the
  throat or exit diameter is not published.

### Interface

- Chart and panel texts follow the interface language (Turkish/English).
- Stability and transient panels show where their numbers come from.
- **OpenRocket corner:** the OpenRocket features are collected in one tab
  in the right sidebar. The RASP motor designation is the impulse-class
  letter plus the average thrust (thrustcurve.org format) instead of the
  case diameter, and the default motor name is no longer cut short when
  OpenRocket reads it.
- The unlinked `/simple` and `/uzaytek` pages were removed.
- The warning for a project saved by an older version follows the interface
  language. The CFD run-time note, the feed-system chart labels and the new
  "Ox Tank (required)" label have Turkish text, and the Turkish interface
  uses one word for "nozzle" throughout.
- The FEA panel shows the load model (pressure distribution, closed-end
  force, scope, force balance) and marks a peak that sits in the loaded end
  band as a diagnosis, not a verdict.
- The solid endpoint no longer declares "APCP, endpoint default" when the
  motor took its propellant from the propellant name or the burn-rate preset
  (example KNDX motor); the numbers are unchanged.
- The Turkish and English user guides (PDF) have v3.0 sections with new
  screenshots: withheld verdicts, thermal results, panel provenance, hybrid
  warnings, CAD export refusals and the map.
- Turkish mode no longer shows leftover English text or decimal points in
  the solid structural tab (risk classes, closure-bolt note), the analysis
  deck's structural and thermal panels, the launch-site vehicle notes and
  load warnings, the uncertainty panel's conditions and the hybrid
  warnings' material names; percentages use the Turkish form (%16,2).
- When the heat module flags its equilibrium wall temperature as not
  physical, the safety panel now says that this is why the thermal axis
  is not evaluated (previously it looked like a missing input).
- Uncertainty analysis: a zero diameter input now means "auto", as it
  does in the engine calculation; the example hybrid motor's uncertainty
  run previously failed with `non_physical_uncertainty_input`.
- CFD run-time note: a viscous run now quotes the viscous worst-case
  table (it used to quote the inviscid figure, e.g. 19.9 s for runs that
  took hundreds of seconds). Both tables were re-measured with one
  protocol (iteration ceiling, shocked back-pressure case, at least two
  repeats); the default level without numba measures 18.5 s. The
  viscous table comes from a loaded machine and is a cautious upper
  bound; the note says so.

### Robustness

- A cached NASA CEA object could be reused after RocketCEA's own cache had
  been cleared, which made some liquid runs fail depending on what ran
  before them. The cache entry is now checked and rebuilt.
- NASA CEA calls ran outside the shared lock. With four parallel threads,
  5 of 5 runs returned silently wrong numbers (for example an ethanol case,
  sea-level Isp 234.909 → 200.404 s). Calls now hold the same lock; serial
  results are bit-identical. When RocketCEA is installed but a call fails,
  the fallback to tabulated data is announced with a warning instead of
  happening silently; the liquid engine reports it as a failed call, not as
  RocketCEA being absent. The isolated NASA CEA data directory is checked
  before use and pinned again if something else moved it.

### Earlier campaign (announced as 2.6.27)

Also in this release, each with before/after numbers in the in-app notes:
ablation physics rebuilt (blowing blockage solved from B′ instead of a
constant 0.5; corrected surface temperatures); the page no longer overrides
the catalogue burn rate; real-gas blowdown pressurant sizing; hybrid
explosive equivalence derived instead of tabulated; the PDF report's safety
section is fed; liquid water hammer (2 → 7 propellants), dump cooling and
power balance; FEA bridge closure margin and thin-wall warning; buckling
envelope and burst-pressure naming; KNDX and KNSB thermochemistry on the
CEA basis; empty form fields are no longer sent and each endpoint declares
the defaults it applied.

### Known limitations

- **2D CFD with back pressure** (`POST /api/cfd/nozzle`, `Pb_Pa`): the
  outlet boundary also imposes the back pressure on cells where the flow is
  reversed. Measured on shocked, over-expanded cases: reversed flow at the
  outlet in 22 of 42 runs in the final field. Every such case already
  returns "not converged / plateau" with a `suspect` separation verdict, so
  none is presented as validated; treat exit-region wall pressure and
  separation output of these runs as qualitative.
- **Supercritical hydrogen coolant velocity.** Channel sizing applies the
  40 m/s liquid-coolant velocity target (NASA SP-8087) to supercritical
  hydrogen as well; a hydrogen-specific target is planned for 3.1. The
  result errs on the safe side (deeper channels, lower coolant-side heat
  transfer, a hotter predicted wall; example LH2 variant: peak hot wall
  1478 K instead of 1387 K, UNSAFE either way), so it does not produce a
  false SAFE.
- **Hybrid TNT equivalent in the API and the PDF report.** The derived
  factor is per kilogram of oxidiser, but the endpoint and the report carry
  no oxidiser-mass input, so it is applied to the total propellant mass.
  The result is too high, on the conservative side (example hybrid:
  5.765 kg TNT; about 5.05 kg on the oxidiser mass). The safety panel does
  not evaluate it for hybrids (see above).
- Star and finocyl grains are not exported to CAD (see above).
- The assembly STL is not a closed solid; use STEP for CAD work.

### Not in this release (planned for 3.1 and later)

- C++ solver core; 3D CFD and 3D FEA; combusting (reactive) CFD; modal FEA.
- CAD with hand-drawn level of detail: injector head and dome, flanges and
  bolt circles, O-ring grooves, ports, regenerative cooling channels, true
  port cross-section, closed STL.
- System parts: turbopump, preburner, feed lines, valves, gimbal; exhaust
  plume visuals.
- A more compact map encoding.
- Gas-only two-phase properties for APCP; validity flags on number-only
  structural fields (liquid mass chain, thickness, mass, T/W).

---

## 3.0.0 — Türkçe

*Yayın tarihi: 2026-10-15.*

HRMA 3.0.0, 2.6.26'dan sonraki ilk sürümdür. Uygulamada "2.6.27
(geliştirme sürüyor)" diye duyurulan çalışma bu sürümle çıkar; ayrı bir
2.6.27 hiç yayımlanmadı.

HRMA bir **ön tasarım aracıdır**: gereksinim → motor → analiz → revizyon →
CAD → ayrıntılı analize aktarım. Uçuş yeterlilik aracı değildir. Bu sürümün
ana fikri şudur: her sayı geçerlilik sınırıyla yayımlanır; modelin
dayanamadığı bir hüküm "geçti" gibi gösterilmez, **gerekçesiyle
bekletilir**.

### Motor fiziği

- **Isıl güvenlik hükümlerinde tek izin sıcaklığı basamağı.** Güvenlik analizi ve ısı
  akısı grafiğindeki servis sınırı artık malzemenin izin sıcaklığını ısıl
  modülle aynı yerden okur. Ölçülen etki: paslanmaz çelik 304/316 1143 →
  1073 K, karbon-karbon 2273 → 1920 K; 1,3'lük pay penceresinde böyle bir
  tasarımın genel riski ORTA'dan YÜKSEK'e çıkar. Kaynağı belirtilmemiş ya da
  okunamayan bir cidar sıcaklığı profili artık olumlu ısıl hüküm almaz.
  Isıl panel hükmü veren sınırı adıyla yazar (düz çelikte yanında yazan
  1073 K izin sıcaklığı değil, 811 K yapısal servis sınırı).
- **Hibrit: N₂O sıvı giriş durumu bir girdidir.** Tank sıcaklığı ve
  oksitleyici fazı yanma entalpi dengesine girer (varsayılan: 293,15 K'de
  doymuş sıvı, CoolProp HEOS; NASA RP-1311 §4.1). Örnek hibrit motorda:
  oda sıcaklığı −56,1 K, c* −%1,195, Isp −%1,175. Gaz fazlı oksitleyiciler
  ile LOX, H₂O₂, hava ve alüminyum vakaları değişmez.
- **Hibrit: N₂O doyma kipinde tank basıncı.** Form, modelin gerçekten
  kullandığı tank basıncını (tank sıcaklığındaki doyma basıncı) salt-okur
  gösterir; istek farklı bir değer gönderirse API uyarır. Örnek hibrit:
  55,0 → 50,5 bar. Tank sıcaklığının enjektör plakası ve motor için tek
  varsayılanı var: 293,15 K (plaka 293 K kullanıyordu).
- **Hibrit kamara malzemesi: tek varsayılan.** Kamara malzemesi vermeyen
  istek artık 4130 çeliği yerine formun zaten seçili gösterdiği 304
  paslanmaz çeliği kullanır ve yanıt bunu beyan eder. Tarayıcıda
  dokunulmamış seçici malzeme göndermiyordu; ekran 304 gösterirken hesap
  4130 ile yapılıyordu. Örnek hibrit: en küçük yapısal emniyet katsayısı
  0,836 → 0,232, kuru kütle 85,16 → 96,80 kg.
- **Hibrit enjektör.** Orifis çapı bandının dört ayrı tanımı yerine tek
  tanımı var (0,5–2,5 mm; Sutton, Mishra); kanonik duş başlığı yolu dışındaki
  planlar değişebilir. Kırpılan basınç düşüşüyle hedef debiyi %5'ten fazla
  kaçıran enjektör planı artık "geçti" almaz (`target_flow_not_met`). Chug
  oranının kalıntısı terim terim ayrıştırılır.
- **Hibrit tane segmentasyonu**, çözücünün hiç kullanmadığı bir segment
  sayısı yerine "modellenmedi" diye bildirilir.
- **Katı APCP termokimyası NASA CEA'dan.** APCP referans kaydı CEA denge
  takımıdır (alev sıcaklığı 3614,8 → 3399,65 K, c* 1598,2 → 1585,4 m/s,
  γ 1,1338, M 27,829 kg/kmol); Bartz ısı transferi bağıntısı aynı koşunun
  donmuş oda γ'sını (1,1862) kullanır. Varsayılan APCP motoru: deniz
  seviyesi Isp +%0,81, boğaz ısı akısı −%2,78. İki faz modülü, kayıt
  yoğuşkan fazı zaten içeriyorsa "yalnız gaz" etkin özelliklerini artık
  yayımlamaz (yoğuşkanı iki kez sayardı).
- **Katı sayfa varsayılanları aynı APCP kaydından gelir.** Taze katı
  sayfada: yoğunluk 1850 → 1810 kg/m³, oda sıcaklığı 3200 → 3399,65 K,
  γ 1,25 → 1,1338, c* 1550 → 1585,4 m/s; deniz seviyesi Isp 206,14 →
  217,60 s, ortalama itki 3134,95 → 3236,30 N, itici kütlesi 6,611 →
  6,468 kg. Düzeltilmiş oda sıcaklığıyla grafit nozul artık nozul aşırı
  sıcaklık uyarısı alır.
- **Güvenlik analizi: itici sınıfı motorun kendi iticisinden.** Kaynaklı
  TNT eşdeğeri olmayan sınıflarda (güvenlik panelinde hibrit, KNDX gibi
  şeker iticiler, kara barut) TNT eşdeğeri, patlama mesafesi, parça menzili
  ve tahliye mesafesi kaynağı olmayan bir sayı yerine gerekçesiyle
  "değerlendirilmedi" olur. API ve PDF raporu panelle aynı kuralı izler:
  katı itici sınıfını katalog ailesinden alır (kompozit, çift bazlı), bu
  yüzden KNDX artık kompozit sayılmaz (1,011 kg TNT, 1600 m tahliye, ORTA →
  değerlendirilmedi, DÜŞÜK). Paneldeki örnek hibrit: 5,435 kg TNT ve
  1600 m tahliye → değerlendirilmedi. APCP ve sıvı sonuçları değişmedi.
- **Güvenlik paneli: fiziksel olmayan cidar sıcaklığından ısıl hüküm
  yok.** Soğutmasız hibritte ısı modülü kendi denge cidar sıcaklığını
  fiziksel değil diye imler; panel artık bu sıcaklığı göndermez, ısıl hüküm
  ve basınç-artı-ısıl birleşik emniyet katsayısı gerekçesiyle bekletilir.
  Örnek hibrit: KRİTİK (birleşik emniyet katsayısı 0,713) → ORTA, kısmi.
- **Yapısal hükümler modelin geçerlilik sınırına uyar.** Yapısal model
  geçerlilik aralığının dışındaysa (örneğin çözülen cidar sıcaklığı yapısal
  analize ulaşmıyorsa) onay hükümleri gerekçesiyle bekletilir: uç kapağı
  "boyutlandırıldı ve doğrulandı", boyutlandırma kipindeki onay, analiz
  güvertesindeki hüküm rozeti ve yapısal güvenlik analizinin tasarım hedefi,
  yorulma ve burkulma hükümleri. Sayılar görünür kalır. 52 vakalık önce/sonra
  ölçümünde 23 vaka "GÜVENLİ · ÇOK DÜŞÜK"ten "DEĞERLENDİRİLMEDİ"ye geçti;
  hiçbir sayı değişmedi, hiçbir başarısız hüküm gizlenmedi. Sıvı yapısal
  kartı, geri okunan tasarım emniyet katsayısı hedefini ve işletme çember
  emniyet katsayısını ayrı adlarla gösterir.
- **Analiz güvertesinin yapısal paneli motorun kendi tasarım hedefini
  kullanır.** Güverte malzeme varsayılanı yerine motorun tasarım emniyet
  katsayısı hedefini gönderir ve kaynağını adıyla yazar. Katı örnek: hedef
  4,0 → 3,0, tasarım hedefi hükmü GÜVENLİ · ÇOK DÜŞÜK → KABUL EDİLEBİLİR ·
  DÜŞÜK; sıvı örnek: 3,0 → 2,5, KABUL EDİLEBİLİR · DÜŞÜK → SINIRDA · ORTA.
- **Yapısal FEA yük modeli.** `/api/fea/structural` yakınsak ve ıraksak
  bölümü 1B izantropik statik basınçla yükler (γ motor sonucundan; yedek
  olarak beyanlı sabit oda basıncı), kapalı uç kuvvetini uygular ve her
  koşuda kuvvet dengesini denetler (tolerans uç kuvvetinin 1e-3'ü; tutmazsa
  hüküm bekletilir). Yanıt kapsamı yazar: yalnız basınç yükü; ısıl gerilme
  ve sıcaklığa bağlı dayanım kapsam dışı. Örnek motorlarda en küçük emniyet
  katsayısı: sıvı 2,23 → 3,63 (HRMA'nın artık boyutlandırdığı cidarla,
  aşağıda), hibrit 5,53 → 9,22, katı 1,03 → 2,19; mesnet yerine duyarlı diye
  bekletilen üç hüküm de artık veriliyor.
- **Sıvı motor kamara cidarını HRMA boyutlandırır.** Sıvı sayfası artık
  kaynaksız 5 mm cidar ön-dolgusu koymaz; cidarı motor boyutlandırır
  (örnek: 2 mm).
- **Rejeneratif soğutma: tek sıcaklık sınırı.** Soğutma hükmünün servis
  sınırı, erime sıcaklığı yerine ısıl modüldeki gibi malzemenin izin
  sıcaklığıdır (bakır 1358 → 723 K, Inconel 718 1533 → 977 K); izin ile
  erime sıcaklığı arasındaki cidar artık UYARI değil GÜVENSİZ alır. Tepe
  cidar sıcaklıkları, ısı yükleri ve basınç düşüşleri değişmedi.
- **Rejeneratif soğutma girdileri motordan gelir.** Soğutma paneli artık
  kaynaksız değer ön-doldurmaz (80 kanal, kanal genişliği ve derinliği,
  astar kalınlığı, su soğutucusu, giriş sıcaklığı ve basıncı): her alan
  motorun yayımladığı değeri alır ya da boş ve zorunlu kalır; zorunlu alan
  boşken istek gönderilmez. `/api/regen-cooling`, `n_channels` taşımayan
  isteğe adlı 400 döner. Soğutucu istasyon marşı koşamadığında ısıl hüküm
  sessizce kaybolmaz, bunu bir uyarı söyler.
- **Süperkritik hidrojen soğutması.** Kanal boyutlandırması ve yayımlanan
  soğutucu hızı aynı hidrojen yoğunluğunu kullanır; önceden boyutlandırma
  sıvı yoğunluğu kullanıyordu ve yayımlanan hız, boyutlandırmanın
  tutturduğunu sandığı hedefin yaklaşık dört katıydı. Hız hedefinin kendisi
  Bilinen sınırlamalar'da.
- **Sıvı sayfasında yakıt yoğunluğu.** Yakıt değişince başka yakıtın
  yoğunluğu girdi diye gitmez (örneğin LH2 için RP-1'in 810 kg/m³'ü); elle
  girilen değer korunur, seçili yakıt farklıysa uyarı gösterilir. Basınç
  beslemeli çevrimde turbopompa verimi ve gaz üreteci sıcaklığı
  kullanılmayan girdiler diye listelenir.

### CAD

- **CAD analiz geometrisinden çizilir (tek kaynak).** Bağımsız bir CAD
  denetimi, dışa aktarıcının yer yer analiz edilen motoru değil kendi
  kuralını çizdiğini bulmuştu (yıldız tane düz boru çiziliyordu, itici
  hacmi +%23,3; hibrit nozul eti STEP'te 3 mm, STL'de 7,19 mm; tank hacmi
  1,23 kat). Bunlar düzeltildi.
- **Fail-closed imalat çıktısı.** Yapısal emniyet katsayısı 1'in altındaysa
  ya da yapısal model geçerlilik aralığının dışındaysa her imalat çıktısı
  (STEP, DXF, çizim PDF'i, STL paketi, tek STL, tam paket,
  `/api/export-cad`) sunucuda aynı adlı gerekçelerle reddedilir (örnek
  hibrit: çizim PDF'i, STL paketi ve `/api/export-cad` 200 → 422). CAD
  çekirdeğinin henüz sadık çizemediği yıldız ve finocyl taneler, dairesel
  port diye dışa aktarılmak yerine gerekçesiyle reddedilir.
- **Her dışa aktarım için tek nozul konturu denetimi.** Geri dönen kontur,
  pozitif olmayan ya da okunamayan boğaz eğrilik yarıçapı ya da okunamayan
  kontur açısı, sessiz bir varsayılana (açılarda 30°, 8° ya da 15°) dayanan
  dosya yerine adlı 422 alır; sunucu hatasına yol açan bozuk kontur bloğu da
  422 alır. Katı ve sıvı CAD paketleri motorun yayımladığı nozul konturunu
  çizer; DXF sınıf tablosu sabit sırayla yazılır (zaman damgası dışında her
  koşuda aynı dosya).
- **Tank modeli** beyanlı düz uçlu silindirdir; parça adları kaynağını
  taşır.
- **Pürüzsüz nozul yüzeyi.** STEP'teki nozul, yüze yakın konik yüzey yerine
  aynı kontur noktalarından geçen tek bir B-spline dönel yüzeydir. Boy ve uç
  çapları bit-aynı; boğaz farkı 1e-7 mm'nin altında. Bozuk kontur sunucu
  hatası yerine adlı 422 hatası döndürür. Paket README'si, bir CAD aracının
  bu yüzeyler için varsayılan hacminin %0,04–1,5 sapabileceğini ve HRMA'nın
  nozul kütlesinin dosyadan okunmadığını yazar.

### Fırlatma sahası haritası

- **Ayrıntılı çevrimdışı harita** (yaklaşık 13 MB paketli varlık): ayrıntı
  düzeyli vektör sınırlar ve yakınlaştırdıkça görünen şehir ve ülke
  etiketleri. Etiketler kar ve buz üstünde okunur kalır; bütün küre
  gösterilirken sayıları sınırlanır.
- **Paketli Dünya görüntüsü.** Paketli NASA Blue Marble dokusu (Aralık
  2004, ekvatorda piksel başına yaklaşık 2 km, 1073 karo, 15,9 MB) hiçbir
  ağ isteği olmadan çizilir; çevrimiçi karolar yalnız daha ince ayrıntı için
  ve yalnız aşağıdaki anahtar açıkken istenir. Harita notu, vektör kıyı
  çizgisi ile görüntü arasındaki ölçülmüş kaymayı yazar (Kennedy kıyısında
  NASA GIBS karosuna karşı: medyan 598 m, 90. yüzdelik 1,3 km).
- **Yer adları**, listelenmiş kısa bir ad kümesinde Türkiye'nin resmî
  kullanımına uyar (örneğin *Türkiye*, *Güney Kıbrıs Rum Yönetimi*,
  *Elazığ*, *Akmescit*); Kırım Ukrayna'nın parçası olarak gösterilir. Öteki
  bütün adlar Natural Earth 5.1.2 ile aynıdır; düzeltmeler haritanın künyesine
  yazılır.
- **Uydu görüntüsü için gizlilik anahtarı.** Görüntü karolarının indirilmesi
  **varsayılan olarak kapalıdır**. Siz açana kadar sunucu dışarıya hiç istek
  atmaz; yerel önbellekteki karolar yine gösterilir.

### Güvenlik

- Yerel API köken kapıları sıkılaştı: başka bir yerel porttaki sayfa yan
  etkili GET uçlarını artık tetikleyemez; portsuz Origin sunucunun gerçek
  portuyla denetlenir.
- İstek gövdesi: her uç için tek 32 MiB sınırı, gövde tamponlanmadan önce
  web sunucusunda uygulanır (sınırı aşan istek JSON 413 alır); konfigürasyon
  ve bileşim listelerinde istek başına kalem sınırı; en çok 100 eşzamanlı
  bağlantı.
- İçerik Güvenliği Politikası'na `object-src 'none'` ve `base-uri 'none'`
  eklendi. Sunucu ve hata metinleri sayfaya girmeden önce kaçışlanır.
- Yükleme ekranları (STEP, OpenRocket `.ork`, motor dosyası, CSV) dosyayı
  göndermeden önce boyut sınırını denetler; sınır sunucudan okunur.
  Doğrulama panelinin yeniden karşılaştırması da denetler; sınırı aşan
  istek (413) okunur bir iletiyle gösterilir.
- Otomatik API bulandırma (fuzz) koşusu (104 uç yöntemi üstünde 3090 istek)
  456 bulgudan 0'a indi: bozuk girdi artık sunucu hatası yerine gerekçeli
  400/422 alır.
- Dışa aktarım uçları bozuk bir iç blokta artık çökmez. İhracat yükünün
  bir iç bloğu (örneğin `design_summary`, `structural_analysis`,
  `heat_transfer_analysis.wall_analysis`, `grain_design`) sözlük yerine
  metin ya da liste gelince dokuz dışa aktarım ucu HTTP 500 veriyordu
  (ölçüldü: 10 720 isteğin 108'i). Artık alanın tam yolunu adlandıran 422
  `invalid_export_geometry` döner; okunamayan `nozzle_angles` bloğu nozul
  konturu kapısının reddini alır. STL paketi ucu, boğaz ya da çıkış çapı
  yayımlanmamışsa 500 yerine montaj üreticisinin adlı reddini döndürür
  (422, `/api/export-cad` gibi).

### Arayüz

- Grafik ve panel metinleri arayüz dilini izler (Türkçe/İngilizce).
- Kararlılık ve geçici rejim panelleri sayılarının nereden geldiğini
  gösterir.
- **OpenRocket köşesi:** OpenRocket özellikleri sağ kenar çubuğunda tek bir
  sekmede toplandı. RASP motor adı kasa çapı yerine itki sınıfı harfi ile
  ortalama itkiden oluşur (thrustcurve.org biçimi); varsayılan motor adı
  OpenRocket okurken artık kırpılmıyor.
- Bağlantısız `/simple` ve `/uzaytek` sayfaları kaldırıldı.
- Eski bir sürümle kaydedilmiş proje uyarısı arayüz dilini izler. CFD
  süre notu, besleme sistemi grafik etiketleri ve yeni "Oksitleyici tankı
  (gerekli basınç)" etiketi Türkçedir; Türkçe arayüz "nozzle" için her
  yerde tek terim (nozul) kullanır.
- FEA paneli yük modelini (basınç dağılımı, kapalı uç kuvveti, kapsam,
  kuvvet dengesi) gösterir; yük uygulanan uç bandındaki tepeyi hüküm değil
  tanı diye işaretler.
- Katı uç, motor iticisini itici adından ya da yanma hızı ön ayarından
  aldığında artık "APCP, uç varsayılanı" beyan etmez (örnek KNDX motoru);
  sayılar değişmedi.
- Türkçe ve İngilizce kullanma kılavuzlarına (PDF) yeni ekran görüntüleriyle
  v3.0 bölümleri eklendi: bekletilen hükümler, ısıl sonuçlar, panel
  künyeleri, hibrit uyarıları, CAD dışa aktarım retleri ve harita.
- Türkçe kipte artık İngilizce kalan metin ve nokta ondalık yok: katı
  Yapısal sekmesi (risk sınıfları, kapak cıvatası notu), analiz
  güvertesinin yapısal ve ısıl panelleri, fırlatma sahasında araç
  künyesi ve yükleme uyarıları, belirsizlik panelinin koşulları ve hibrit
  uyarılarındaki malzeme adları; yüzde Türkçe biçimde (%16,2).
- Isı modülü kendi denge cidar sıcaklığını fiziksel değil diye
  işaretlediğinde güvenlik paneli, ısıl eksenin bu yüzden
  değerlendirilmediğini söyler (önceden eksik girdi gibi görünüyordu).
- Belirsizlik analizi: sıfır çap girdisi, motor hesabında olduğu gibi
  "otomatik" demektir; örnek hibrit motorun belirsizlik koşusu önceden
  `non_physical_uncertainty_input` ile düşüyordu.
- CFD süre notu: viskoz koşu artık viskoz en kötü hâl tablosunu söyler
  (önceden viskozsuz değeri söylüyordu; örneğin yüzlerce saniye süren
  koşularda 19,9 s). İki tablo tek protokolle yeniden ölçüldü (yineleme
  tavanı, şoklu geri basınçlı vaka, en az iki tekrar); varsayılan seviye
  numba olmadan 18,5 s ölçüldü. Viskoz tablo yüklü makineden gelir ve
  temkinli bir üst sınırdır; not bunu söyler.

### Kararlılık

- Önbellekteki bir NASA CEA nesnesi, RocketCEA'nın kendi önbelleği
  boşaltıldıktan sonra yeniden kullanılabiliyordu; bu, bazı sıvı motor
  koşularını kendinden önce ne koştuğuna göre düşürüyordu. Önbellek kaydı
  artık denetlenip yeniden kurulur.
- NASA CEA çağrıları ortak kilidin dışında koşuyordu. Dört paralel iş
  parçacığında 5 koşunun 5'i sessizce yanlış sayı döndürdü (örneğin bir
  etanol vakasında deniz seviyesi Isp 234,909 → 200,404 s). Çağrılar artık
  aynı kilidi tutar; seri sonuçlar bit-aynı. RocketCEA kuruluyken bir çağrı
  başarısız olursa tablo verisine geçiş sessiz olmaz, uyarıyla bildirilir;
  sıvı motor bunu RocketCEA yok diye değil, başarısız çağrı diye bildirir.
  Yalıtılmış NASA CEA veri dizini kullanılmadan önce denetlenir, başka bir
  bileşen onu kaydırmışsa yeniden sabitlenir.

### Önceki kampanya (2.6.27 diye duyurulan)

Bu sürümde ayrıca şunlar var; her birinin önce/sonra sayıları uygulama
içi notlarda: ablasyon fiziği yeniden kuruldu (üfleme blokajı sabit 0,5
yerine B′'den çözülür; yüzey sıcaklıkları düzeltildi); sayfa artık katalog
yanma hızını ezmiyor; basınçlandırıcı boyutlandırmasında gerçek gaz; hibrit
patlayıcı eşdeğeri tablodan okunmaz, türetilir; PDF raporunun güvenlik
bölümü besleniyor; sıvı motorda su koçu (2 → 7 itici), dump soğutma ve güç
dengesi; FEA köprüsünde kapama tabanı payı ve ince cidar uyarısı; burkulma
zarfı ve kopma basıncı adı; KNDX ve KNSB termokimyası CEA tabanında; boş
form alanları artık gönderilmez ve her uç uyguladığı varsayılanları beyan
eder.

### Bilinen sınırlamalar

- **Geri basınçlı 2B CFD** (`POST /api/cfd/nozzle`, `Pb_Pa`): çıkış sınır
  koşulu, akışın ters döndüğü hücrelere de geri basıncı dayatır. Şoklu,
  aşırı genişlemiş vakalarda ölçüldü: 42 koşunun 22'sinde son alanda çıkışta
  geri akış var. Bu vakaların hepsi zaten "yakınsamadı / plato" ve `suspect`
  ayrılma hükmüyle döner, hiçbiri doğrulanmış diye sunulmaz; bu koşularda
  çıkış bölgesindeki duvar basıncını ve ayrılma çıktısını nitel kabul edin.
- **Süperkritik hidrojen soğutucu hızı.** Kanal boyutlandırması 40 m/s
  sıvı soğutucu hız hedefini (NASA SP-8087) süperkritik hidrojene de
  uygular; hidrojene özgü hedef 3.1'e planlandı. Sonuç güvenli yönde sapar
  (daha derin kanal, daha düşük soğutucu tarafı ısı transferi, daha sıcak
  öngörülen cidar; örnek LH2 varyantı: tepe sıcak cidar 1387 K yerine
  1478 K, iki durumda da GÜVENSİZ), yani yanlış bir GÜVENLİ üretmez.
- **API ve PDF raporunda hibrit TNT eşdeğeri.** Türetilmiş çarpan kilogram
  oksitleyici başınadır, ama uç ve rapor oksitleyici kütlesi girdisi
  taşımadığı için toplam itici kütlesine uygulanır. Sonuç ihtiyatlı yönde
  fazladır (örnek hibrit: 5,765 kg TNT; oksitleyici kütlesiyle yaklaşık
  5,05 kg). Güvenlik paneli hibritte bunu değerlendirmez (yukarıya bakın).
- Yıldız ve finocyl taneler CAD'e aktarılmaz (yukarıya bakın).
- Montaj STL'i kapalı bir katı değildir; CAD işi için STEP kullanın.

### Bu sürümde yok (3.1 ve sonrasına planlandı)

- C++ çözücü çekirdeği; 3B CFD ve 3B FEA; yanmalı (reaktif) CFD; modal FEA.
- Elle çizilmiş ayrıntıda CAD: enjektör kafası ve domu, flanşlar ve cıvata
  dairesi, O-ring kanalları, portlar, rejeneratif soğutma kanalları, gerçek
  port kesiti, kapalı STL.
- Sistem parçaları: turbopompa, ön yakıcı, besleme hatları, valfler,
  gimbal; egzoz plümü görselleri.
- Daha sıkı harita kodlaması.
- APCP için yalnız gaz iki faz özellikleri; yalnız sayı taşıyan yapısal
  alanlarda (sıvı kütle zinciri, kalınlık, kütle, T/W) geçerlilik bayrakları.

---

Earlier versions: see `packaging/release_notes_v*.md` and the in-app
Release Notes window. · Önceki sürümler: `packaging/release_notes_v*.md`
ve uygulama içi Sürüm Notları penceresi.
