# HRMA - Hybrid Rocket Motor Analysis

A comprehensive web-based tool for designing and analyzing hybrid, solid, and liquid rocket motors. Input your parameters, get optimized motor geometry, performance metrics, and 3D visualizations.

## Features

- **Three Motor Types**: Hybrid (HTPB/N2O, etc.), Solid (APCP, KNSB, etc.), Liquid (RP-1/LOX, LH2/LOX, etc.)
- **Optimal Design Output**: Nozzle angles, grain geometry, injector sizing, wall thickness — all calculated from first principles
- **3D Visualization**: Interactive Plotly-based motor assembly views
- **NASA CEA Integration**: Real thermochemical data via RocketCEA
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
│   └── static/             # CSS & JS
├── data/                   # Runtime databases & cache
├── tests/                  # Test suite
└── docs/                   # Documentation
```

## Requirements

- Python 3.10+
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
   - 3D motor visualization
   - Exportable STL/CAD files

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

**HRMA v2.0**
- Developed by: Berke Tezgocen
- Idea & Testing: Ayberk Cem Aksoy
- Professional Rocket Propulsion Design Tool
- Last Updated: 2026

## Ready to Design?

1. **Clone the repo**
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Run**: `python run.py`
4. **Open**: `http://localhost:8080`
5. **Start designing rockets!**

## License

MIT
