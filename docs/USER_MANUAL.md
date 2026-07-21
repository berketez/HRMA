# HRMA User Manual

HRMA (UZAYTEK Rocket Motor Analysis) is a desktop application for the
preliminary design and analysis of hybrid, solid, and liquid rocket motors.
It runs a local Flask engine behind a native desktop window (pywebview) and
presents results in a dark-themed web interface with an interactive 3D
digital twin, an Analysis Deck of engineering panels, and working CAD /
drawing / report exports.

This manual describes HRMA **v2.5.5**.

> **Scope notice.** HRMA is a preliminary-design and educational tool built
> on closed-form and 1D engineering correlations. It is not a
> flight-qualification tool. See "Scope and Limitations" at the end of this
> manual and [VALIDATION_STATUS.md](VALIDATION_STATUS.md) for what has been
> verified and what has not.

## Table of Contents

1. [Installation](#1-installation)
2. [First Launch](#2-first-launch)
3. [Main Pages](#3-main-pages)
4. [The Calculate Workflow (Hybrid Page)](#4-the-calculate-workflow-hybrid-page)
5. [Reading the Results](#5-reading-the-results)
6. [Standalone Panels: Transient, Injector, 6-DOF](#6-standalone-panels-transient-injector-6-dof)
7. [The Analysis Deck](#7-the-analysis-deck)
8. [3D Digital Twin](#8-3d-digital-twin)
9. [Exports](#9-exports)
10. [Kinetic Fidelity Levels](#10-kinetic-fidelity-levels)
11. [Validating Against Your Own Test Data](#11-validating-against-your-own-test-data)
12. [Automatic Updates](#12-automatic-updates)
13. [Troubleshooting](#13-troubleshooting)
14. [Scope and Limitations](#14-scope-and-limitations)
15. [Saving and Reusing Projects](#15-saving-and-reusing-projects)
16. [Importing External Designs](#16-importing-external-designs)

---

## 1. Installation

### Option A: Windows installer (recommended on Windows)

1. Download `HRMA-Setup-2.5.5.exe` from the
   [latest release](https://github.com/berketez/HRMA/releases/latest).
2. Double-click and follow the wizard (Next, Next, Install). The installer
   is per-user: no administrator rights are required.
3. Windows SmartScreen may warn because the installer is unsigned: click
   "More info", then "Run anyway".

Python and all libraries are bundled; no separate installation is needed.

### Option B: macOS disk image (recommended on macOS)

1. Download `HRMA-Setup-2.5.5-macOS.dmg` from the
   [latest release](https://github.com/berketez/HRMA/releases/latest)
   (Apple Silicon, macOS 11 or newer).
2. Open the DMG and drag `HRMA` into `Applications`.
3. On first launch, right-click the app and choose "Open" (Gatekeeper
   requires this once for unsigned apps).

### Option C: from source (developers)

```bash
git clone https://github.com/berketez/HRMA.git
cd HRMA
pip install -r requirements.txt
python hrma/run.py
```

Requirements: Python 3.10-3.13 (3.12 recommended; 3.14 is not supported yet
because compiled dependencies require `numpy<2`). The app serves on
`http://localhost:8080` (waitress) and opens your browser automatically.

Optional extras for source installs:

- `build123d`: enables true STEP solid export (the packaged installers
  include it).
- `cantera`: enables the High-Fidelity kinetic level (without it, kinetic
  requests gracefully fall back to the Engineering level and say so).

## 2. First Launch

The packaged app opens a splash screen within about a second while the
calculation engines load in the background, then shows the home page in its
own native window (WKWebView on macOS, WebView2 on Windows, so Chrome is not
required). Everything runs locally and offline; no analysis data leaves your
computer. At startup HRMA checks GitHub Releases for a newer version (see
[Automatic Updates](#12-automatic-updates)). This is the only network
access, and it fails silently when offline.

CAD, drawing, and report outputs are written to `Documents/HRMA`.

## 3. Main Pages

| Page | URL | Purpose |
|---|---|---|
| Home | `/` | Motor-type selection cards (Hybrid / Solid / Liquid) and a link to the formula reference |
| Hybrid Designer | `/hybrid` | Full hybrid motor design and analysis (the most complete page) |
| Solid Designer | `/solid` | Solid motor design: grain geometry, ballistics, Monte Carlo |
| Liquid Designer | `/liquid` | Liquid engine design: feed system, injector, regenerative cooling |
| Formula Reference | `/formulas` | The equations used by the solvers, rendered with MathJax |

All three designer pages share the same structure: an input form, a
Calculate button, a results HUD, standalone panels (transient / injector /
6-DOF where applicable), the Analysis Deck, the 3D digital twin, and export
buttons.

## 4. The Calculate Workflow (Hybrid Page)

Fill the form top to bottom, then press **Calculate**. The main input groups:

### Mission and operating point

- **Motor name**: free text, used in exports and reports.
- **Altitude**: single altitude (ambient pressure is derived automatically)
  or an altitude range for altitude-swept performance.
- **Thrust [N] and burn time [s]**, or alternatively **total impulse [N·s]**
  (the form derives the missing pair member).

### Combustion

- **O/F ratio**: oxidizer-to-fuel mass ratio. The "Find Optimum" helper
  (`/api/find-optimum-of`) sweeps O/F and suggests the c*-optimal value.
- **Chamber pressure [bar]** and **tank pressure [bar]**: the form warns
  when tank pressure does not sufficiently exceed chamber pressure.
- **Combustion model**: equilibrium thermochemistry is computed by the
  built-in Cantera-based solver; propellant data is cross-checked against
  NASA CEA (see VALIDATION_STATUS.md).

### Geometry

- **L\* [m]**: characteristic chamber length.
- **Expansion ratio**: enter 0 for automatic (ambient-pressure adapted)
  calculation.
- **Nozzle type**: conical or bell.
- **Chamber diameter, contraction ratio, chamber mass flux**: enter 0 to
  let the solver size them.

### Fuel

- **Fuel type**: HTPB, paraffin, PE, PMMA, ABS, PLA, or a user mixture
  (paraffin / carbon / Al2O3 / aluminum / HTPB percentages with automatic
  density update).
- **Density, regression coefficients a and n**: defaults are
  literature values for the selected fuel; override them with your own
  fitted coefficients when you have static-fire data.

### Oxidizer

- **Oxidizer type and phase** (N2O, LOX, H2O2; liquid or gas), density,
  viscosity, and temperature (density auto-updates with temperature for
  self-pressurizing N2O).

### Injector

- **Injector type**: showerhead, pintle, or swirl, with type-specific
  parameters (target velocity, hole diameter limits, plate thickness).
  For detailed injector design use the dedicated Injector Design panel
  (Section 6), which implements the Dyer NHNE two-phase model for
  self-pressurizing N2O.

The solid and liquid pages follow the same pattern with type-specific
inputs (grain geometry, segments, and propellant family on the solid page;
propellant pair, feed system type, and cooling inputs on the liquid page).

## 5. Reading the Results

Pressing Calculate sends the form to `/calculate` (or `/calculate_solid`,
`/calculate_liquid`) and populates:

- **Results HUD**: animated stat cards for the headline numbers: thrust,
  total impulse, Isp, c*, CF, chamber pressure, throat and exit diameters,
  fuel/oxidizer mass flow, and a SAFE / MARGINAL / UNSAFE state badge.
- **Warnings panel**: design-criteria messages from the solver and the
  validation system (for example injector pressure-drop ratio, L/D limits,
  regression-model applicability). Read these before trusting the numbers.
- **Motor design tables**: full geometry: nozzle contour dimensions and
  angles, grain/port geometry, injector plan, wall thickness.
- **Performance charts**: Plotly charts (thrust curve, pressure, altitude
  sweeps) in the same dark theme, fully offline.
- **2D cross-section**: engineering cross-section drawing generated from
  the same geometry the solver used.

Interactive design mode: after a calculation, the chamber diameter, L*, and
expansion-ratio sliders recompute geometry in about a second
(`/api/quick-geometry`) and update the 3D model and the 2D cross-section
live, without a full recalculation.

## 6. Standalone Panels: Transient, Injector, 6-DOF

These panels sit below the main results and chain onto the computed design.

### Transient Ballistics (hybrid page)

`/api/transient-analysis` marches the coupled chamber/feed equations in
time and returns the real Pc(t) and F(t) histories:

- **Feed mode**: regulated (constant feed pressure) or self-pressurizing
  N2O blowdown (equilibrium two-phase tank model; tank pressure and
  temperature decay are part of the result).
- **Stability guards**: NASA SP-8089 injector pressure-drop margins are
  checked at every time step and reported as warnings.
- The resulting thrust curve feeds the OpenRocket `.eng` export, the 6-DOF
  panel, and the burn animation of the 3D digital twin.

### Injector Design (hybrid and liquid pages)

`/api/injector-design` performs detailed injector sizing for seven element
types (showerhead, unlike/like impinging doublets and triplets, pintle,
swirl, coaxial shear). For self-pressurizing N2O it uses the **Dyer NHNE
two-phase model** (blend of single-phase incompressible and homogeneous
equilibrium flow) instead of the optimistic single-phase orifice equation.
Outputs: hole plan (count, diameter, pattern), pressure drop, discharge
behavior, spray/atomization estimates, manifold checks, and design
warnings. Fields are pre-filled from the current motor result and can be
overridden.

### 6-DOF Flight (all three pages)

`/api/six-dof-analysis` runs a rigid-body six-degree-of-freedom flight
simulation on top of the computed thrust curve: quaternion attitude,
Barrowman CN_alpha / CP stability derivatives, static margin,
weathercocking into wind, and apogee. Use it for stability screening
(small angle-of-attack aerodynamics), not for tumbling or large-alpha
flight.

## 7. The Analysis Deck

The Analysis Deck is a tabbed panel container (categories: THERMAL,
STRUCTURAL, SAFETY, PERFORMANCE, PRESSURE VESSEL, FLOW, VALIDATION, and
more) that appears after a successful calculation. Every panel:

- pre-fills its input fields from the current motor result (suggestions
  only, so anything you edit by hand is preserved and never overwritten),
- POSTs the form to its own API endpoint when you press Run Analysis,
- renders tables, stat cards, and Plotly charts, with ok / warning / error
  badges.

The 13 panels (introduced through v2.4.6, current in v2.5.5):

| Panel | Endpoint | Motor types | What it computes |
|---|---|---|---|
| Structural Safety | `/analyze_structural_safety` | all | Pressure-vessel stress (Lame, thick/thin wall), buckling (NASA SP-8007 knockdown), fatigue, temperature-derated safety factors against the materials database |
| Thermal Safety | `/analyze_thermal_safety` + `/api/analysis/wall-profile` | all | Bartz gas-side heat transfer, wall temperatures vs material limits, and an axial heat-flux / wall-temperature / Mach profile along the chamber-nozzle axis |
| Comprehensive Safety | `/analyze_safety` | all | Combined risk assessment: pressure-vessel margins, failure modes, hazard ranking |
| Advanced Performance | `/api/advanced-performance-analysis` | all | 3D performance surface, Mach contour, and heat-flux map over the operating envelope |
| Pressure Vessel | `/api/pressure-vessel-analysis` | all | Vessel sizing, MAWP, and real burst-pressure estimate for the selected material and weld efficiency |
| Thermal Protection | `/api/thermal-protection` | all | Ablative, heat-sink, and radiation-cooled liner sizing; in-depth wall temperature profile at end of burn and hot-face temperature history |
| Bolted Joint | `/api/bolted-joint` | all | Closure-bolt preload, tightening torque, and joint-separation margins (Shigley method) |
| Nozzle Flow | `/api/flow-analysis` (+ `/api/kinetic-efficiency` probe) | all | Quasi-1D compressible nozzle flow: regime detection, P(x), M(x), CF; reports which kinetic fidelity level was actually used |
| User Data Validation | `/api/validation/upload-csv` | all | Compares your own static-fire CSV against the HRMA prediction (Section 11) |
| Regenerative Cooling | `/api/regen-cooling` | liquid only | 1D station march along the chamber-nozzle axis: Bartz gas side, Dittus-Boelter coolant side, wall and coolant temperatures, heat flux, coolant pressure drop |
| Feed System | `/api/slosh-analysis`, `/api/pressurant-sizing`, `/api/water-hammer` | liquid + hybrid (water hammer: all) | Tank slosh frequencies and slosh mass vs fill level, pressurant gas sizing, and water-hammer surge pressure from valve closure |
| Injector Design | `/api/injector-design` | hybrid + liquid | See Section 6 |
| Comparative Analysis | `/api/comparative-analysis` | all | Side-by-side comparison of multiple saved motor configurations (thrust, Isp, total impulse, mass) with best-in-metric ranking (new in v2.4.6) |

Panels marked "long" warn you that the analysis may take noticeably longer
(for example the high-fidelity kinetic integration).

### Uncertainty and Correlation (v2.5.0 Confidence Release)

Two additional panels live in the Analysis Deck on the hybrid (`/hybrid`),
solid (`/solid`) and liquid (`/liquid`) pages. Like the other panels, they
appear only after a successful **Calculate** and pre-fill from the current
motor result.

#### Uncertainty (`/api/uncertainty-analysis`)

This panel propagates the uncertainty of the design inputs through the whole
solver with a Monte Carlo run (Latin Hypercube sampling) and reports how
uncertain each output is.

Controls:

- **Analysis Level**: `fast` / `engineering` / `high_fidelity`, trading speed
  for sample count (200 / 1000 / 3000 samples; Engineering is the sensible
  default, High-Fidelity is the "long" setting).
- **Seed**: the random seed; keeping it fixed makes a run exactly
  reproducible.
- **Run**: executes the analysis and draws the results.

How to read it:

- Each output is reported as **P50 with a [P5, P95] band**. P50 is the median
  (the "middle" prediction); the [P5, P95] interval is a 90 % credible range,
  there is a 90 % chance the true value lies inside it given the input
  uncertainties you supplied. A wide band means the result is poorly
  constrained, not that the nominal number is wrong.
- The **sensitivity tornado** ranks the inputs by how strongly they drive the
  output. The bar length is the **Spearman rank correlation** between that
  input and the output over the Monte Carlo sample, and it captures monotonic
  effects only (an input that pushes the result up when it goes up, or vice
  versa). The longest bars are the parameters worth measuring or controlling
  most tightly; near-zero bars barely matter.

#### Correlation (`/api/correlation-report`)

This panel scores HRMA's predictions against the built-in real-experiment
validation database (published, fully-cited hybrid, solid and liquid firing
data) and shows a per-quantity accuracy table.

Controls:

- **Run / Refresh**: computes the correlation report. The result is cached by
  the content hash of the experiment database, so if nothing in the database
  changed a **CACHED** badge appears and the cached report is shown instantly
  instead of recomputing.
- **Layers**: the table is split into `main`, `low`, and `anomaly`. `main` is
  the trustworthy body of statistics (high/medium-confidence records);
  `low` isolates low-confidence records; `anomaly` aggregates records that were
  flagged as anomalous (cracked grain, nozzle failure, etc.) separately.

How to read it:

- The signed error convention is **(predicted − measured) / measured × 100**:
  a positive value means HRMA over-predicts, negative means it under-predicts.
- **Outliers are flagged but never dropped**: a bad point stays in the table
  and in the statistics, marked, so the numbers stay honest.
- **Anomaly-flagged records do not enter the main statistics.** They are
  reported in their own `anomaly` layer so that a known-bad firing does not
  distort the headline accuracy.

The live correlation numbers change whenever the database changes, so treat the
panel (and the auto-generated block in VALIDATION_STATUS.md) as the current
source of truth rather than any figure quoted elsewhere.

## 8. 3D Digital Twin

The Three.js/WebGL viewer builds a parametric 3D motor directly from the
solver output, not a canned model. Features:

- **Cutaway view**: quarter-section of chamber, grain, injector, nozzle.
- **Burn animation**: the port opens over time following the computed
  regression history (from the transient analysis when available).
- **Exploded view** and dimension labels.
- **Wall heat-flux map**: chamber and nozzle surfaces colored by the
  Bartz-distributed heat flux, anchored to the heat-transfer module's
  real q and wall-temperature values.
- **Exhaust plume** visualization.
- Grain port cross-sections: circular, star, multi-port, and finocyl
  (area-equivalent visualization; ballistics uses the circular-equivalent
  port).

## 9. Exports

All exports are generated from the same geometry the solver produced
(single source of truth). Files are written to `Documents/HRMA` (packaged
app) or a temporary directory (source runs), and offered as downloads.

| Export | Endpoint | Notes |
|---|---|---|
| STL solids | `/api/export-stl`, `/api/export-stl-zip` | Watertight solids revolved from the real nozzle contour; injector orifices are actually drilled (manifold3d booleans) |
| STEP solid | `/api/export-step` | True parametric STEP (AP214) via build123d/OpenCascade; returns an explanatory error if build123d is not installed (bundled in the installers) |
| DXF profiles | `/api/export-dxf` | Layered 2D manufacturing profiles (ezdxf) |
| Technical drawing PDF | `/api/export-drawings-pdf` | Multi-page dimensioned drawing set |
| OpenRocket `.eng` | `/api/export-eng` | Uses the real computed thrust curve when a transient analysis has been run, otherwise the design-point curve |
| Analysis report PDF | `/api/export-pdf/<type>` | Formatted report of inputs, results, and warnings |
| Complete package ZIP | `/api/export-complete-zip` | STL + STEP + DXF + drawing PDF + `.eng` + geometry in one archive |

## 10. Kinetic Fidelity Levels

Kinetic-efficiency estimates (finite-rate combustion losses) are offered at
three explicit levels; the response always reports both
`fidelity_requested` and `fidelity_used` so you know what you actually got:

- **Fast Screening (`fast`)**: correlation-based estimate, instant.
- **Engineering (`engineering`)**: the default: reduced physics-based
  model, suitable for trade studies.
- **High-Fidelity (`high_fidelity`)**: finite-rate species integration
  (Cantera, BDF) along the nozzle. Requires the optional `cantera`
  package; if Cantera is not installed the request degrades gracefully to
  the Engineering level and says so in the result.

The Nozzle Flow panel probes the kinetic module and displays which level is
available on your installation.

## 11. Validating Against Your Own Test Data

The **User Data Validation** panel compares HRMA's predicted thrust curve
with your own static-fire measurement:

1. Run a calculation (and ideally a transient analysis, since the comparison
   then uses the real F(t) curve instead of a constant-thrust rectangle).
2. Open the panel, paste your CSV or choose a file. Expected format: two
   numeric columns, time [s] and thrust [N]; the parser reports what it
   understood (point count, warnings).
3. Press the panel's upload button. The panel overlays both curves and
   reports quantitative metrics with a grade (excellent / good / fair /
   poor) and an assessment text.

This is the honest way to close the loop: fit your measured regression
coefficients back into the fuel inputs and re-run.

## 12. Automatic Updates

At startup HRMA queries the GitHub Releases API for the repository
`berketez/HRMA`. If a newer tagged version exists, a modal offers a
one-click update. The updater selects the asset itself by file suffix
(`.dmg` on macOS, `.exe` on Windows); no URL from outside the GitHub API
is ever used. When offline, the check fails silently and the app runs
normally.

Since v2.5.5 the update is fully automatic: after you click "Update
now", HRMA downloads the installer (verifying its size and, when GitHub
provides one, its SHA-256 digest), closes itself, installs the new
version silently and reopens on its own. No drag-and-drop and no
"Replace?" dialog is involved.

Safety behavior:

- On macOS the old application is kept until the new version has
  actually started; if the new version fails to launch, the previous
  version is restored automatically.
- If HRMA is running from source, from inside a mounted DMG, from a
  non-writable location, or the disk is nearly full, the silent path is
  skipped and the downloaded installer is simply opened for a manual
  install (the pre-2.5.5 behavior).
- Every step is logged to `Documents/HRMA/hrma_update_log.txt`. On any
  failure the installer file is left in your Downloads folder and opened
  so you can finish the update manually.
- On Windows a small console window shows progress while the silent
  install runs; do not close it — HRMA reopens automatically when it
  finishes.

## 13. Troubleshooting

**Port 8080 already in use.** HRMA serves on `http://localhost:8080`.
Find and stop the conflicting process:

```bash
# macOS / Linux
lsof -ti:8080 | xargs kill -9

# Windows
netstat -ano | findstr :8080
taskkill /PID <PID_NUMBER> /F
```

**Window opens but stays blank / spinning.** Wait a few seconds on first
launch (engines are loading); if it persists, quit and relaunch. On source
runs, check the terminal for a Python traceback.

**`numpy` version errors (source install).** HRMA requires `numpy<2`
because several compiled dependencies (CoolProp, manifold3d, build123d)
are built against the NumPy 1.x ABI. Fix with:

```bash
pip install "numpy<2"
```

**Python 3.14 not supported.** Use Python 3.10-3.13 (3.12 recommended).
`run.py` refuses to start on unsupported interpreters with a clear message.

**STEP export returns an error (source install).** Install the optional
dependency: `pip install build123d "numpy<2"`. The packaged installers
already include it.

**High-Fidelity kinetics falls back to Engineering.** Install the optional
`cantera` package. The fallback is intentional and reported, not a bug.

**macOS: "app can't be opened" on first launch.** Right-click the app and
choose Open (unsigned app, Gatekeeper requires one manual confirmation).

**Windows SmartScreen blocks the installer.** Click "More info", then
"Run anyway" (the installer is unsigned).

**Results look wrong.** Read the warnings panel first. Most "wrong"
results are inputs outside the validity range of the underlying
correlations, and the validation system flags them.

## 14. Scope and Limitations

HRMA operates at the **hand-calculation / preliminary-design level**:
closed-form relations, empirical correlations, quasi-1D flow, and 1D
thermal marches. It is deliberately not a high-fidelity simulation
environment:

- **No finite-element analysis.** Structural margins come from Lame
  thick-wall relations, SP-8007 buckling knockdowns, and Shigley joint
  methods, not FEA. For detailed stress analysis of a flight design, use
  a dedicated FEA package (for example ANSYS Mechanical or CalculiX) and
  a hydrostatic proof test.
- **No CFD.** The nozzle flow is quasi-1D compressible; injector spray
  and combustion-chamber flow fields are correlation-based. For internal
  flow detail, use a CFD code (for example ANSYS Fluent or OpenFOAM).
- **No combustion-instability prediction.** SP-8089 pressure-drop margins
  screen for feed-coupled instability; acoustic modes (chug/screech) are
  demonstrated on the test stand, not in software.
- **Empirical uncertainty.** Hybrid regression rates carry a documented
  ±20-30 % band; heat transfer (Bartz) is ±20-30 %. See
  [VALIDATION_STATUS.md](VALIDATION_STATUS.md) for the complete, honest
  list of verification anchors and known limitations.

Use HRMA to converge a design and narrow a test matrix. Cross-check any
serious design against an independent tool (NASA CEA, RPA, openMotor) and
verify by physical testing before firing any motor.

## 15. Saving and Reusing Projects

Since v2.5.5 every design page (hybrid, solid, liquid) has a project bar
at the top: **Save / Save As / Open / New**. Projects are stored as
`.hrma` files (plain JSON) under `Documents/HRMA/projects` — one file per
project, portable and diff-friendly. A saved project contains all form
inputs, the active tab states, any analysis-deck fields you edited by
hand, and a small summary of the last computed results.

Behavior notes:

- An asterisk next to the project name marks unsaved changes; the browser
  warns before you leave the page with unsaved work.
- Opening a project of a different motor type redirects you to the right
  page automatically (`?project=<name>` in the URL).
- The landing page lists your most recent projects for one-click access.
- Deleting a project moves it to `Documents/HRMA/projects/.trash` rather
  than erasing it; corrupt files are flagged in the list but never crash
  it. Loading never invents missing fields — a project written by a
  different HRMA version loads with a warning instead of silent guesses.

## 16. Importing External Designs

v2.5.5 adds the reverse of the design workflow: bring an existing design
into HRMA and turn it into numbers.

**Thrust curve files (.eng RASP / .rse RockSim).** The validation panel
(section 11) accepts these directly, alongside CSV. HRMA overlays the
imported catalog/test curve on its own prediction and reports the same
comparison metrics (total impulse, peak/average thrust, burn time, RMSE,
grade). In the 6-DOF panel an imported motor file can also be selected as
the thrust source, so you can fly your airframe on a catalog motor. An
`.rse` file may contain several motors — a selector appears.

**OpenRocket rockets (.ork).** The 6-DOF panel's "Import .ork" button
maps the rocket's nose, body, fins and mass components onto HRMA's
flight-dynamics inputs. Masses that OpenRocket stores only as
density-times-geometry arrive marked *estimated* and stay editable. A
mapping report lists everything that was mapped, approximated or skipped
(parachutes and rail buttons do not affect the aerodynamic model, for
example). If the file contains OpenRocket's own saved simulation results,
HRMA shows a side-by-side comparison card after your 6-DOF run.

**CAD solids (.step/.stp).** "Import from CAD (STEP)" on the design
pages analyzes the solid, finds the motor axis and every cylindrical or
conical surface, and proposes measurement candidates for throat, exit,
chamber diameter/length and wall thickness on top of a cross-section
drawing. Nothing is applied silently: you confirm or correct each
dimension, then apply them to the design form, choose materials and
propellants (a CAD file carries neither), and run the normal analysis.
Suggestions that cannot be derived from the geometry are simply absent —
HRMA does not guess. Assemblies prompt you to pick which solid to
analyze; inch-unit files are converted to millimeters with a warning.
