#!/bin/bash

# Rocket Motor Analysis - Cross-platform Startup Script

echo "=========================================="
echo "  ROCKET MOTOR ANALYSIS TOOL"
echo "=========================================="
echo

# Function to check for Python
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        return 0
    elif command -v python &> /dev/null; then
        # Check if it's Python 3
        if python -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)' 2>/dev/null; then
            PYTHON_CMD="python"
            return 0
        fi
    fi
    return 1
}

# Check for Python installation
if ! check_python; then
    echo "Error: Python 3.7+ is not installed!"
    echo
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "On macOS, install Python with:"
        echo "  brew install python3"
        echo "  or download from: https://www.python.org/downloads/"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "On Linux, install Python with:"
        echo "  sudo apt update && sudo apt install python3 python3-pip"
        echo "  or: sudo yum install python3 python3-pip"
    fi
    echo
    exit 1
fi

echo "Found Python: $PYTHON_CMD"
$PYTHON_CMD --version
echo

# Python surum kapisi: 3.10-3.13 desteklenir. 3.14+ derlenmis bagimliliklar
# (numpy<2, CoolProp, RocketCEA) icin wheel bulamayip kaynaktan derlemeye
# calisiyor ve C derleyicisi olmadan patliyor (2026-07-15 numpy meson hatasi).
PYMAJ=$($PYTHON_CMD -c 'import sys; print(sys.version_info[0])')
PYMIN=$($PYTHON_CMD -c 'import sys; print(sys.version_info[1])')
if [ "$PYMAJ" -ne 3 ]; then
    echo "Error: Python 3.10-3.13 required. Detected: $PYMAJ.$PYMIN"
    exit 1
fi
if [ "$PYMIN" -lt 10 ]; then
    echo "Error: Python 3.10 or newer required. Detected: 3.$PYMIN"
    exit 1
fi
if [ "$PYMIN" -ge 14 ]; then
    echo "=========================================================="
    echo "  Python 3.$PYMIN is not supported for source install."
    echo "=========================================================="
    echo "Compiled dependencies numpy, CoolProp, RocketCEA do not ship"
    echo "3.14+ wheels, so pip tries to build them from source and fails"
    echo "without a C compiler."
    echo
    echo "EASIEST FIX: download the ready-made installer instead of the"
    echo "source code: https://github.com/berketez/HRMA/releases/latest"
    echo "  macOS: HRMA-Setup-x.y.z-macOS.dmg  (bundles Python 3.12 + everything)"
    echo
    echo "Or install Python 3.12 from https://www.python.org/downloads/"
    exit 1
fi

# Check for pip
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "Installing pip..."
    $PYTHON_CMD -m ensurepip --upgrade
fi

echo "Installing required packages..."
echo "This may take a few minutes on first run..."
echo

# Upgrade pip
$PYTHON_CMD -m pip install --upgrade pip

# Install required packages
$PYTHON_CMD -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo
    echo "Error: Failed to install required packages!"
    echo
    echo "Common solutions:"
    echo "1. Check your internet connection"
    echo "2. Try: $PYTHON_CMD -m pip install --user flask flask-cors numpy scipy plotly pandas"
    echo "3. On some systems, you might need: sudo $PYTHON_CMD -m pip install -r requirements.txt"
    echo
    exit 1
fi

echo
echo "Installation completed successfully!"
echo
echo "Starting web application..."
echo "The browser will open automatically at: http://localhost:8080"
echo
echo "Press Ctrl+C to stop the application"
echo

# Make run.py executable
chmod +x hrma/run.py

# Start the application
$PYTHON_CMD hrma/run.py