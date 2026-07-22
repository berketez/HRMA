# Installation Guide - HRMA

## Easiest Path: Use the Installers

If you just want to use HRMA, you do not need Python or this guide. Download
`HRMA-Setup-X.Y.Z.exe` (Windows) or `HRMA-Setup-X.Y.Z-macOS.dmg` (macOS) from
the [latest release](https://github.com/berketez/HRMA/releases/latest).
Everything (Python, all libraries, offline charts) is bundled.

The rest of this guide covers **installing from source** (developers, Linux
users, or anyone who prefers running the code directly).

## Requirements

- **Python 3.10-3.13** (3.12 recommended). Python 3.14 is **not** supported
  yet: HRMA pins `numpy<2` because several compiled dependencies (CoolProp,
  manifold3d, build123d) are built against the NumPy 1.x ABI, and those
  wheels do not exist for 3.14.
- **RAM**: 2 GB available
- **Storage**: ~1 GB free (packages included)
- **Internet**: required only for the initial package installation

Supported platforms: Windows 10/11, macOS 11+ (Apple Silicon and Intel),
Linux (Ubuntu 20.04+, Debian 11+, Fedora, etc.).

## Quick Start

### Windows

1. Install Python 3.10-3.13 from [python.org](https://www.python.org/downloads/)
   (check "Add Python to PATH" during installation)
2. Download or clone the repository
3. Double-click `start.bat`
4. Wait for automatic installation; the app opens at http://localhost:8080

### macOS / Linux

```bash
git clone https://github.com/berketez/HRMA.git
cd HRMA
chmod +x start.sh && ./start.sh
```

## Manual Installation

### Step 1: Verify Python version

```bash
python3 --version   # must print 3.10.x - 3.13.x
```

### Step 2: Install dependencies

```bash
# Recommended: from the requirements file
pip install -r requirements.txt

# Or use the helper installer
python3 hrma/install.py
```

### Step 3: Run the application

```bash
python3 hrma/run.py
```

The server (waitress) listens on **http://localhost:8080** and your browser
opens automatically.

### Optional extras

```bash
pip install cantera               # High-Fidelity kinetic level
```

Without it, kinetic requests gracefully fall back to the Engineering level.

**STEP export (`build123d`) — separate environment required.** build123d
0.11.x declares `numpy>=2`, while HRMA pins `numpy<2` (see the ABI note at
the top of this file). Installing it into the pinned environment silently
upgrades NumPy to 2.x and breaks the solver — verified on CI 2026-07-23,
where the upgrade removed `np.trapz` and failed 194 tests. So:

- In the pinned environment, STEP export is unavailable; the endpoint returns
  an explanatory error rather than failing silently, and STEP tests skip.
- To use STEP export from source, create a **separate** environment with
  NumPy 2.x, or use the desktop installers, which bundle a working
  build123d/NumPy combination.

Migrating HRMA itself to NumPy 2 (16 `np.trapz` call sites) is planned as a
separate task; it would remove this split.

## File Structure

```
HRMA/
├── start.bat               # Windows launcher
├── start.sh                # macOS/Linux launcher
├── requirements.txt        # Python dependencies
├── hrma/                   # Main package
│   ├── run.py              # Application launcher (developers)
│   ├── app.py              # Flask web application
│   ├── constants.py        # Shared constants
│   ├── install.py          # Dependency helper installer
│   ├── engines/            # Motor solvers (hybrid/solid/liquid, combustion,
│   │                       #   nozzle, injector)
│   ├── analysis/           # Engineering analyses (thermal, structural,
│   │                       #   transient, 6-DOF, feed system, quasi-1D flow, ...)
│   ├── data/               # Propellant/chemical/materials databases
│   ├── export/             # STL/STEP/DXF/drawing-PDF/.eng/report generation
│   ├── validation/         # Verification & user-data validation
│   ├── visualization/      # Plotly chart builders
│   ├── utils/              # Helpers, update checker, job runner
│   ├── templates/          # HTML pages (index, hybrid, solid, liquid, formulas)
│   └── static/             # CSS + JS (Three.js 3D viz, Analysis Deck panels)
├── data/                   # Runtime databases & cache (created on first run)
├── packaging/              # Installer build scripts (developers only)
├── tests/                  # Automated test suite
└── docs/                   # Documentation
```

## Dependencies

Installed automatically from `requirements.txt`; the main ones:

- **Flask** + **waitress**: local web server behind the UI
- **NumPy (<2)**, **SciPy**: numerical computing
- **Plotly**: interactive charts (bundled offline)
- **CoolProp**: real-fluid thermodynamic properties (N2O blowdown, etc.)
- **RocketCEA**: NASA CEA cross-checks
- **Cantera** (optional): equilibrium/finite-rate combustion chemistry
- **ezdxf**, **manifold3d**, **reportlab**: DXF, STL boolean, and PDF outputs
- **pywebview**: native desktop window (packaged app)

## Troubleshooting

### "Python is not recognized"

**Windows:**
- Reinstall Python with "Add to PATH" checked, or add it manually

**macOS/Linux:**
- Try `python3` instead of `python`

### "Permission denied" (macOS/Linux)

```bash
chmod +x start.sh
./start.sh
```

### "pip is not recognized"

```bash
python -m pip install -r requirements.txt
# or
python3 -m pip install -r requirements.txt
# or (Windows)
py -m pip install -r requirements.txt
```

### "Port 8080 already in use"

**Windows:**
```cmd
netstat -ano | findstr :8080
taskkill /PID <PID_NUMBER> /F
```

**macOS/Linux:**
```bash
lsof -ti:8080 | xargs kill -9
```

### NumPy / compiled-package errors

HRMA requires `numpy<2`. If another tool upgraded NumPy:

```bash
pip install "numpy<2"
```

If you are on Python 3.14, downgrade to 3.10-3.13, because the compiled
dependencies have no 3.14 wheels yet, and `hrma/run.py` refuses unsupported
interpreters with a clear message.

### Installation fails on corporate networks

```bash
pip install --trusted-host pypi.org --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org -r requirements.txt
```

### Slow installation

- The first installation downloads a few hundred MB of packages
- Subsequent runs are much faster

### Platform notes

**Windows**: Microsoft Store Python works; antivirus may slow the first
installation.

**macOS**: Homebrew Python is fine (`brew install python@3.12`); Xcode
Command Line Tools may be required for compiled packages.

**Linux**: you may need development packages:
`sudo apt install python3-dev build-essential`.

## Advanced Installation

### Virtual environment (recommended for developers)

```bash
python3 -m venv hrma_env

# Windows:
hrma_env\Scripts\activate
# macOS/Linux:
source hrma_env/bin/activate

pip install -r requirements.txt
python hrma/run.py
```

### Conda

```bash
conda create -n hrma python=3.12
conda activate hrma
pip install -r requirements.txt
python hrma/run.py
```

### Docker (advanced users)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "hrma/run.py"]
```

## Success Indicators

When everything works, the terminal shows the server starting on
http://localhost:8080, your browser opens automatically, and you can enter
motor parameters and press Calculate on the hybrid/solid/liquid pages.

---

**Need usage help?** See [USER_MANUAL.md](docs/USER_MANUAL.md) and the main
[README.md](README.md).
