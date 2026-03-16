# Installation Guide - Hybrid Rocket Motor Analysis Tool

## Universal Cross-Platform Installation

This tool works on **Windows**, **macOS**, and **Linux** with Python 3.7+.

## Quick Start (Recommended)

### Windows Users:
1. **Download** all files to a folder
2. **Double-click** `start.bat`
3. **Wait** for automatic installation and browser opening

### Mac/Linux Users:
1. **Download** all files to a folder
2. **Open terminal** in the folder
3. **Run**: `chmod +x start.sh && ./start.sh`
4. **Wait** for automatic installation and browser opening

## Manual Installation

### Step 1: Install Python
- **Windows**: Download from [python.org](https://www.python.org/downloads/) 
  - ⚠️ **Important**: Check "Add Python to PATH" during installation
- **Mac**: `brew install python3` or download from python.org
- **Linux**: `sudo apt install python3 python3-pip` or `sudo yum install python3 python3-pip`

### Step 2: Verify Installation
```bash
# Check Python version (should be 3.7+)
python --version
# or
python3 --version
```

### Step 3: Install Dependencies
```bash
# Option 1: Automatic (recommended)
python install.py

# Option 2: Manual
pip install flask flask-cors numpy scipy plotly pandas waitress

# Option 3: From requirements file
pip install -r requirements.txt
```

### Step 4: Run Application
```bash
# Simple method
python run.py

# Or use platform scripts
# Windows: start.bat
# Mac/Linux: ./start.sh
```

## File Structure

```
HRMA/
├── start.bat              # Windows launcher
├── start.sh               # Mac/Linux launcher  
├── install.py             # Cross-platform installer
├── run.py                 # Main application launcher
├── app.py                 # Flask web application
├── requirements.txt       # Python dependencies
├── hybrid_rocket_engine.py # Motor calculations
├── injector_design.py     # Injector algorithms
├── visualization.py       # Plotting functions
├── templates/
│   └── index.html         # Web interface
├── static/
│   ├── css/style.css      # Styling
│   └── js/app.js          # Frontend logic
└── README.md              # Documentation
```

## System Requirements

### Minimum Requirements:
- **Python**: 3.7 or higher
- **RAM**: 512 MB available
- **Storage**: 100 MB free space
- **Internet**: Required for initial package installation

### Supported Operating Systems:
- ✅ **Windows 7/8/10/11** (32-bit and 64-bit)
- ✅ **macOS 10.13+** (High Sierra and newer)
- ✅ **Linux** (Ubuntu, Debian, CentOS, Fedora, etc.)

### Supported Python Installations:
- ✅ **Official Python** (python.org)
- ✅ **Microsoft Store Python** (Windows)
- ✅ **Homebrew Python** (macOS)
- ✅ **System Python** (Linux distributions)
- ✅ **Anaconda/Miniconda**
- ✅ **PyPy** (partial compatibility)

## Dependencies

The application automatically installs these packages:

- **Flask**: Web framework for the user interface
- **Flask-CORS**: Cross-origin resource sharing
- **NumPy**: Numerical computing
- **SciPy**: Scientific computing and optimization
- **Plotly**: Interactive visualizations
- **Pandas**: Data manipulation
- **Waitress** (Windows) / **Gunicorn** (Unix): Production web servers

## Troubleshooting

### Common Issues:

#### "Python is not recognized"
**Windows:**
- Reinstall Python with "Add to PATH" checked
- Or manually add Python to PATH environment variable

**Mac/Linux:**
- Try `python3` instead of `python`
- Install with package manager: `brew install python3` (Mac) or `sudo apt install python3` (Linux)

#### "Permission denied" (Mac/Linux)
```bash
chmod +x start.sh
./start.sh
```

#### "pip is not recognized"
```bash
# Try these alternatives:
python -m pip install -r requirements.txt
python3 -m pip install -r requirements.txt
py -m pip install -r requirements.txt
```

#### "Port 5000 already in use"
**Windows:**
```cmd
netstat -ano | findstr :5000
taskkill /PID <PID_NUMBER> /F
```

**Mac/Linux:**
```bash
lsof -ti:5000 | xargs kill -9
```

#### Installation fails on corporate networks
- Use: `pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt`
- Or contact IT department about Python package installation

#### Slow installation
- The first installation downloads ~200MB of packages
- Subsequent runs are much faster
- Use `pip install --cache-dir ./cache -r requirements.txt` for offline cache

### Platform-Specific Notes:

#### Windows:
- Tested on Windows 7, 8, 10, 11
- Both 32-bit and 64-bit supported
- Microsoft Store Python works
- Antivirus may slow first-time installation

#### macOS:
- Requires macOS 10.13+ (High Sierra)
- Both Intel and Apple Silicon (M1/M2) supported
- Homebrew Python recommended: `brew install python3`
- May need to install Xcode Command Line Tools

#### Linux:
- Tested on Ubuntu 18.04+, CentOS 7+, Debian 9+
- Both x86_64 and ARM64 supported
- May need development packages: `sudo apt install python3-dev build-essential`

## Advanced Installation

### Using Virtual Environment (Recommended for developers):
```bash
# Create virtual environment
python -m venv hrma_env

# Activate virtual environment
# Windows:
hrma_env\Scripts\activate
# Mac/Linux:
source hrma_env/bin/activate

# Install packages
pip install -r requirements.txt

# Run application
python run.py
```

### Using Conda:
```bash
# Create conda environment
conda create -n hrma python=3.9
conda activate hrma

# Install packages
pip install -r requirements.txt

# Run application
python run.py
```

### Docker (for advanced users):
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "run.py"]
```

## Getting Help

### Before seeking help:
1. ✅ **Run the installer**: `python install.py`
2. ✅ **Check Python version**: `python --version` (should be 3.7+)
3. ✅ **Try the simple command**: `python run.py`
4. ✅ **Check the browser**: Open http://localhost:5000 manually

### Error Logs:
- Errors are displayed in the terminal/command prompt
- Screenshot error messages when reporting issues
- Include your operating system and Python version

### Common Solutions:
- **Restart** your computer after Python installation
- **Update pip**: `python -m pip install --upgrade pip`
- **Clear pip cache**: `pip cache purge`
- **Try user installation**: `pip install --user -r requirements.txt`

## Success Indicators

When everything works correctly, you should see:
```
==========================================
  HYBRID ROCKET MOTOR ANALYSIS TOOL
  http://localhost:5000
==========================================

Platform: Windows 10.0.19041
Starting web server...
Press Ctrl+C to stop

✓ Browser should open automatically
✓ Web interface loads at http://localhost:5000
✓ You can enter motor parameters and calculate
```

---

**Need more help?** Check the main README.md file for usage instructions.