# HRMA - High-Fidelity Rocket Motor Analysis

A comprehensive web-based tool for designing and analyzing hybrid, solid, and liquid rocket motors. Input your parameters, get optimized motor geometry, performance metrics, and an interactive 3D digital twin of your motor.

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
- **6-DOF Flight Panel** (all three motor pages): Barrowman stability (CN_α/CP, static margin), weathercocking, apogee — chains directly onto the computed thrust curve
- **NASA CEA Integration**: Real thermochemical data via RocketCEA; hybrid thermochemistry computed by the built-in Cantera equilibrium solver
- **Performance Analysis**: Thrust curves, Isp, trajectory simulation, heat transfer, structural analysis
- **Export**: STL files, OpenRocket .eng files, PDF reports

## Validation

HRMA's thermochemistry is cross-checked against **NASA CEA** (via RocketCEA):
hybrid combustion (c\*, Tc, Isp) agrees within **≤1.5 %** across all supported
fuel/oxidizer pairs, and liquid c\* within **<2 %**. The hybrid regression model
is compared against published static-fire data (Rezaei HTPB/N2O). 127 automated
tests pass.

HRMA is a **preliminary-design and educational tool**, not a flight-qualification
tool. Predicted performance should be cross-checked against an independent code
(CEA / RPA / openMotor) and verified by physical testing before firing any motor.
See [VALIDATION_STATUS.md](VALIDATION_STATUS.md) for full verification results,
uncertainty bands, and known limitations.

## Quick Start

```bash
git clone https://github.com/berketez/HRMA.git
cd HRMA
pip install -r requirements.txt
python run.py
```

Open http://localhost:8080 in your browser.

## Project Structure

```
HRMA/
├── run.py                  # Entry point
├── hrma/                   # Main package
│   ├── app.py              # Flask web application (48 routes)
│   ├── engines/            # Motor calculations
│   │   ├── hybrid_rocket_engine.py
│   │   ├── solid_rocket_engine.py
│   │   ├── liquid_rocket_engine.py
│   │   ├── combustion_analysis.py
│   │   └── nozzle_design.py
│   ├── analysis/           # Engineering analysis
│   │   ├── cfd_analysis.py
│   │   ├── heat_transfer_analysis.py
│   │   ├── structural_analysis.py
│   │   ├── safety_analysis.py
│   │   ├── trajectory_analysis.py
│   │   └── ...
│   ├── data/               # Data sources & APIs
│   │   ├── propellant_database.py
│   │   ├── chemical_database.py
│   │   ├── web_propellant_api.py
│   │   ├── nasa_realtime_validator.py
│   │   └── ...
│   ├── export/             # Output generation
│   │   ├── cad_export.py
│   │   ├── cad_visualization.py
│   │   ├── openrocket_integration.py
│   │   └── pdf_generator.py
│   ├── validation/         # Verification & validation
│   ├── visualization/      # Plotly charts & dashboards
│   ├── utils/              # Helpers & utilities
│   ├── templates/          # HTML templates
│   └── static/             # Dark theme CSS + JS (Three.js motor viz, Plotly wrappers)
├── data/                   # Runtime databases & cache
├── tests/                  # Test suite
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

**HRMA v2.1**
- Developed by: Berke Tezgocen
- Idea & Testing: Ayberk Cem Aksoy
- Professional Rocket Propulsion Design Tool
- Last Updated: July 2026 (dark mission-control UI, Three.js digital twin, interactive design mode)

## Ready to Design?

1. **Clone the repo**
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Run**: `python run.py`
4. **Open**: `http://localhost:8080`
5. **Start designing rockets!**

## License

MIT
