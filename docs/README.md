# HRMA Documentation Index

HRMA (UZAYTEK Rocket Motor Analysis) is a desktop application for
preliminary design and analysis of hybrid, solid, and liquid rocket motors:
a local Flask engine behind a native window (pywebview), a dark-themed UI
with a 13-panel Analysis Deck, a Three.js 3D digital twin, and working
STL/STEP/DXF/drawing-PDF/report exports.

## Primary documents (repository root)

| Document | Content |
|---|---|
| [`README.md`](../README.md) | Product overview, features, downloads, real project structure |
| [`USER_MANUAL.md`](USER_MANUAL.md) | Installation and usage: pages, Calculate workflow, Analysis Deck panels, exports, troubleshooting |
| [`INSTALL.md`](../INSTALL.md) | Source installation (developers) |
| [`RELEASE.md`](RELEASE.md) | How releases are built and published; how the in-app updater works |
| [`VALIDATION_STATUS.md`](VALIDATION_STATUS.md) | Verification anchors, known limitations, honest reliability envelope |
| [`SPACE_CAPABILITY.md`](SPACE_CAPABILITY.md) | Capability assessment for Karman-class preliminary design |

## Documents in this directory

| Document | Content |
|---|---|
| [`ANALIZ_PLATFORM_PLANI.md`](ANALIZ_PLATFORM_PLANI.md) | Analysis platform plan (Turkish) — implemented in waves 0-4B, shipped in v2.4.x |
| [`10_Enjektor_ARGE.md`](10_Enjektor_ARGE.md) | Injector design R&D report and the `injector_design.py` API contract (Turkish; implemented) |
| [`PACKAGE_MIGRATION_PLAN.md`](PACKAGE_MIGRATION_PLAN.md) | Historical plan for the flat-layout to `hrma/` package migration (executed) |
| `bolum2_termodinamik_nozzle.md` ... `bolum9_yorunge_analizi.md` | Theory derivations (Turkish) tied to the real code paths: thermodynamics/nozzle, combustion chemistry, hybrid, solid, liquid, heat transfer, structural, trajectory |
| [`visualization_modules.md`](visualization_modules.md) | Reference for the Plotly visualization functions |
| [`archive/`](archive/README.md) | Early aspirational/fictional documentation — kept as history, does **not** describe the product |

## Where things live in the code

```
hrma/
├── app.py            # Flask routes (~73)
├── run.py            # Launcher: waitress on http://localhost:8080
├── engines/          # hybrid/solid/liquid solvers, combustion, nozzle, injector
├── analysis/         # thermal, structural, transient, 6-DOF, feed system,
│                     #   quasi-1D nozzle flow, kinetic fidelity levels
├── data/             # propellant / chemical / materials databases
├── export/           # STL, STEP, DXF, drawing PDF, .eng, report PDF
├── validation/       # verification & user static-fire CSV validation
├── visualization/    # Plotly chart builders
├── templates/        # index, hybrid, solid, liquid, formulas pages
└── static/           # theme CSS, Three.js digital twin, Analysis Deck panels
```
