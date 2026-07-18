# HRMA - High-Fidelity Rocket Motor Analysis

A comprehensive desktop tool for designing and analyzing hybrid, solid, and liquid rocket motors. Input your parameters, get optimized motor geometry, performance metrics, and an interactive 3D digital twin of your motor.

## Just Want to Use HRMA? Download the Installer

**You do not need Python, the source code, or anything on this page.** Grab the
installer for your platform from the
[**latest release**](https://github.com/berketez/HRMA/releases/latest), run it,
and you're done:

| Platform | Direct download |
|---|---|
| **Windows 10/11** | [**HRMA-Setup-2.5.0.exe**](https://github.com/berketez/HRMA/releases/download/v2.5.0/HRMA-Setup-2.5.0.exe) — double-click, Next → Next → Install |
| **macOS 11+ (Apple Silicon)** | [**HRMA-Setup-2.5.0-macOS.dmg**](https://github.com/berketez/HRMA/releases/download/v2.5.0/HRMA-Setup-2.5.0-macOS.dmg) — drag HRMA to Applications |

Everything is bundled (Python, all libraries, offline charts). HRMA opens in
its own native window and notifies you automatically when a new version is
available. All the folders and files below are **source code for developers** —
you can ignore them entirely.

## Features

- **Three Motor Types**: Hybrid (HTPB/N2O, etc.), Solid (APCP, KNSB, etc.), Liquid (RP-1/LOX, LH2/LOX, etc.)
- **Optimal Design Output**: Nozzle angles, grain geometry, injector sizing, wall thickness — all calculated from first principles
- **3D Digital Twin (Three.js/WebGL)**: Parametric motor simulation built live from solver output — cutaway view, burn animation driven by the computed port regression history, exploded view, dimension labels, and exhaust plume
- **Interactive Design Mode**: Chamber diameter / L* / expansion ratio sliders with ~1 s geometry recompute (`/api/quick-geometry`); 3D model and 2D cross-section update live
- **Grain Port Cross-Sections**: Circular, star, multi-port, and finocyl port shapes (area-equivalent visualization; ballistics solved with the circular-equivalent port)
- **Wall Heat-Flux Map**: Chamber/nozzle surface colored by Bartz-distributed heat flux with real q and T_wall anchors from the heat transfer module
- **Real-Geometry CAD Export**: STL solids revolved from the same nozzle contour used by the solver and the 2D drawing (watertight, single source of truth); injector orifices actually drilled (manifold3d booleans)
- **STEP / DXF / Drawing PDF**: true parametric STEP solids (build123d/OpenCascade), layered DXF manufacturing profiles (ezdxf), and multi-page dimensioned technical-drawing PDFs — plus a one-click complete design package ZIP (STL+STEP+DXF+PDF+.eng+geometry)
- **Transient Ballistics Panel**: time-resolved Pc(t)/F(t) with regulated or self-pressurizing N₂O blowdown feed, SP-8089 injector-stability margins; the OpenRocket `.eng` export uses the real computed thrust curve
- **Full Feature Parity Across Motor Types**: motor design tables, engineering cross-section drawings, working CAD/PDF/.eng exports, trajectory and safety reports on the hybrid, solid **and** liquid pages
- **Solid Motor Monte Carlo**: manufacturing-tolerance uncertainty analysis (burn-rate a/n, density, C*; 300 samples in <1 s) with success rate, statistics and thrust/Isp histograms
- **Uncertainty Quantification (v2.5.0 Confidence Release)**: full-design Monte Carlo with Latin Hypercube sampling, reported as P50 median with a [P5, P95] 90 % credible interval per output, plus a Spearman rank-correlation sensitivity tornado that ranks which input uncertainties drive each result; three explicit effort levels (`fast` / `engineering` / `high_fidelity`, 200 / 1000 / 3000 samples) and a fixed seed for reproducibility (`/api/uncertainty-analysis`, available on the hybrid, solid and liquid pages)
- **Real-Experiment Validation Database (v2.5.0 Confidence Release)**: a git-tracked JSON database of published, fully-cited real firing data (hybrid, solid and liquid static-fire points plus published engine specs and strand burn-rate data) with a hard `inputs`/`measured` separation that structurally prevents circular validation; an automatic correlation report (`/api/correlation-report`, cached by database content hash) scores HRMA predictions against the measurements and writes the summary into VALIDATION_STATUS.md
- **Exact Star Grain Regression**: burning perimeter computed by geometric offset of the true star profile (Huygens principle, validated against the analytic circular-port solution) — point count and depth feed directly into the thrust curve
- **Liquid Engine Flow Schematic**: feed-system diagram (tanks → turbopump/pressure-fed → injector → chamber → nozzle) generated from computed flow rates and pressures
- **6-DOF Flight Panel** (all three motor pages): Barrowman stability (CN_α/CP, static margin), weathercocking, apogee — chains directly onto the computed thrust curve
- **Analysis Deck (13 panels)**: tabbed engineering-analysis deck that pre-fills from the current motor result — Structural Safety (Lamé/SP-8007/fatigue), Thermal Safety (Bartz + axial wall profile), Comprehensive Safety, Advanced Performance (3D surface, Mach contour), Pressure Vessel (MAWP/burst), Thermal Protection (ablative/heat-sink/radiation-cooled), Bolted Joint (Shigley), Nozzle Flow (quasi-1D), User Data Validation (static-fire CSV), Regenerative Cooling (liquid), Feed System (slosh/pressurant/water hammer), Injector Design, and Comparative Analysis
- **Quasi-1D Nozzle Flow**: compressible quasi-1D solver with regime detection, P(x)/M(x) profiles and CF — replaces the former placeholder CFD panel
- **Staged Combustion Kinetics**: three explicit fidelity levels (Fast Screening / Engineering / High-Fidelity finite-rate Cantera integration) with honest `fidelity_used` reporting and graceful fallback when Cantera is absent
- **Materials Database**: 11 engineering materials (steels, aluminum, titanium, Inconel, coppers, graphite, ablative liner) with temperature-derated properties feeding the structural and thermal panels
- **Injector Design Module**: seven element types with the Dyer NHNE two-phase model for self-pressurizing N₂O (not the optimistic single-phase orifice equation)
- **Gas Radiation (Leckner)**: chamber radiation uses Leckner H₂O/CO₂ gas emissivity correlations instead of a black-body assumption
- **Native Desktop App**: opens in its own window (macOS WKWebView / Windows WebView2 — no Chrome required), splash screen appears in ~1 s while engines load in the background; closing the window closes the app
- **Automatic Updates**: checks GitHub Releases at startup and offers one-click download & install of new versions
- **Fully Offline**: all JS libraries (Plotly, Three.js, MathJax) are bundled — no CDN, no internet required after installation
- **NASA CEA Integration**: Real thermochemical data via RocketCEA; hybrid thermochemistry computed by the built-in Cantera equilibrium solver
- **Performance Analysis**: Thrust curves, Isp, trajectory simulation, heat transfer, structural analysis
- **Export**: STL files, OpenRocket .eng files, PDF reports

## Validation

HRMA's thermochemistry is cross-checked against **NASA CEA** (via RocketCEA):
hybrid combustion (c\*, Tc, Isp) agrees within **≤1.5 %** across all supported
fuel/oxidizer pairs, and liquid c\* within **<2 %**. 1,000+ automated tests pass.

As of the **v2.5.0 Confidence Release**, HRMA also carries a git-tracked
database of real, fully-cited firing data (hybrid, solid and liquid), and an
automated correlation runner scores the predictions against it. The current
correlation statistics (bias, median absolute percent error, RMS, per-quantity
sample counts and worst-case tests) are machine-generated and change with every
run, so they are **not duplicated here** — see the auto-generated correlation
block in [VALIDATION_STATUS.md](VALIDATION_STATUS.md) (the section "Automated
correlation snapshot", between the `AUTO-CORRELATION` markers) for the live
numbers. The signed-error convention there is `(predicted − measured) / measured
× 100`; outliers are flagged but never dropped, and anomaly-flagged records are
aggregated separately from the main statistics.

HRMA is a **preliminary-design and educational tool**, not a flight-qualification
tool. Predicted performance should be cross-checked against an independent code
(CEA / RPA / openMotor) and verified by physical testing before firing any motor.
See [VALIDATION_STATUS.md](VALIDATION_STATUS.md) for full verification results,
uncertainty bands, and known limitations.

## Installation (No Python Required)

One-click installers with Python 3.12 and **all** dependencies embedded — no
internet connection, no admin rights, no terminal needed:

Download the latest installers from the
[**Releases page**](https://github.com/berketez/HRMA/releases/latest):

| Platform | Installer | Notes |
|---|---|---|
| **Windows 10/11** | [`HRMA-Setup-2.5.0.exe`](https://github.com/berketez/HRMA/releases/download/v2.5.0/HRMA-Setup-2.5.0.exe) | English setup wizard (Next → Next → Install); per-user, desktop shortcut, no admin rights |
| **macOS 11+ (Apple Silicon)** | [`HRMA-Setup-2.5.0-macOS.dmg`](https://github.com/berketez/HRMA/releases/download/v2.5.0/HRMA-Setup-2.5.0-macOS.dmg) | Drag & drop to Applications; right-click → Open on first launch |

Once installed, HRMA notifies you at startup when a new version is released
and updates itself with one click.

The installers are unsigned: Windows SmartScreen shows "More info → Run anyway",
macOS Gatekeeper needs right-click → Open once. CAD and drawing outputs are
written to `Documents/HRMA`. Build pipeline and reproduction instructions:
[`packaging/`](packaging/README.md).

## Quick Start (Developers)

```bash
git clone https://github.com/berketez/HRMA.git
cd HRMA
pip install -r requirements.txt
python hrma/run.py
```

Open http://localhost:8080 in your browser.

## Project Structure

```
HRMA/
├── start.sh / start.bat    # Developer launch scripts
├── hrma/                   # Main package
│   ├── app.py              # Flask web application (~73 routes)
│   ├── run.py              # Launcher (waitress on port 8080)
│   ├── constants.py        # Shared physical constants & parameters
│   ├── engines/            # Motor calculations
│   │   ├── hybrid_rocket_engine.py
│   │   ├── solid_rocket_engine.py
│   │   ├── liquid_rocket_engine.py
│   │   ├── combustion_analysis.py
│   │   ├── injector_design.py      # 7 element types, Dyer NHNE two-phase
│   │   └── nozzle_design.py
│   ├── analysis/           # Engineering analysis
│   │   ├── nozzle_flow_1d.py       # Quasi-1D compressible nozzle flow
│   │   ├── kinetic_efficiency.py   # Fast / Engineering / High-Fidelity kinetics
│   │   ├── heat_transfer_analysis.py
│   │   ├── structural_analysis.py
│   │   ├── pressure_vessel.py
│   │   ├── thermal_protection.py
│   │   ├── bolted_joint.py
│   │   ├── regen_cooling.py
│   │   ├── slosh_analysis.py / pressurant_sizing.py / water_hammer.py
│   │   ├── transient_ballistics.py / tank_blowdown.py
│   │   ├── six_dof_trajectory.py / trajectory_analysis.py
│   │   ├── safety_analysis.py / safety_limits.py
│   │   └── ...
│   ├── data/               # Data sources & databases
│   │   ├── propellant_database.py
│   │   ├── materials_db.py         # 11 engineering materials
│   │   ├── chemical_database.py
│   │   └── ...
│   ├── export/             # Output generation
│   │   ├── cad_export.py / step_export.py
│   │   ├── drawing_generator.py / motor_geometry.py
│   │   ├── openrocket_integration.py
│   │   └── pdf_generator.py
│   ├── validation/         # Verification & validation
│   ├── visualization/      # Plotly charts & dashboards
│   ├── utils/              # Helpers, update checker, job runner
│   ├── templates/          # HTML templates (index, hybrid, solid, liquid, formulas)
│   └── static/             # Dark theme CSS + JS (Three.js viz, Analysis Deck panels)
├── data/                   # Runtime databases & cache
├── packaging/              # Installer build scripts (dmg / exe) & release tooling
├── tests/                  # Test suite (1,000+ automated tests)
└── docs/                   # Documentation
```

## Requirements

- Python 3.10–3.13 (**3.12 recommended**; 3.14 not supported yet — compiled dependencies lack wheels)
- Flask, NumPy, SciPy, Plotly, Matplotlib
- RocketCEA (NASA CEA wrapper)
- CoolProp (thermodynamic properties)
- See `requirements.txt` for full list

## How It Works

1. **Input**: Enter motor parameters (thrust, chamber pressure, fuel type, O/F ratio, etc.)
2. **Calculate**: Engine computes optimal geometry using isentropic flow relations, Saint-Robert burn rate law, and NASA CEA thermochemistry
3. **Output**: Get a complete design package:
   - Nozzle dimensions and angles (convergent/divergent)
   - Grain geometry (web thickness, segments, Kn range)
   - Injector sizing (orifice diameter, pressure drop)
   - Performance metrics (Isp, c*, CF, thrust curve)
   - Interactive 3D digital twin (cutaway, burn animation, heat map)
   - Exportable STL/CAD files generated from the real solver geometry

## Key Equations

**Thrust Coefficient:**

$$C_F = \lambda \sqrt{\frac{2\gamma^2}{\gamma-1} \left(\frac{2}{\gamma+1}\right)^{\frac{\gamma+1}{\gamma-1}} \left[1-\left(\frac{P_e}{P_c}\right)^{\frac{\gamma-1}{\gamma}}\right]} + \frac{(P_e - P_a) \cdot \varepsilon}{P_c}$$

**Characteristic Velocity:**

$$c^* = \frac{\sqrt{\gamma R T_c}}{\gamma \left(\frac{2}{\gamma+1}\right)^{\frac{\gamma+1}{2(\gamma-1)}}}$$

**Throat Area:**

$$A_t = \frac{\dot{m} \cdot c^*}{P_c}$$

**Burn Rate (solid):**

$$r = a \cdot P_c^n \quad \text{(Saint-Robert's law)}$$

## Version

**HRMA v2.4.6**
- Developed by: Berke Tezgocen
- Idea & Testing: Ayberk Cem Aksoy
- Professional Rocket Propulsion Design Tool
- Last Updated: July 2026 (13-panel Analysis Deck with comparative analysis,
  quasi-1D nozzle flow, staged combustion kinetics, materials database,
  Leckner gas-emissivity radiation, NHNE injector design, physics-audit
  fixes, native desktop window with automatic updates via GitHub Releases)

## Ready to Design?

1. **Clone the repo**
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Run**: `python hrma/run.py`
4. **Open**: `http://localhost:8080`
5. **Start designing rockets!**

## License

MIT
