#!/bin/bash

# Hybrid Rocket Motor Analysis - Cross-platform Startup Script

echo "=========================================="
echo "  HYBRID ROCKET MOTOR ANALYSIS TOOL"
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
echo "The browser will open automatically at: http://localhost:5000"
echo
echo "Press Ctrl+C to stop the application"
echo

# Make run.py executable
chmod +x run.py

# Start the application
$PYTHON_CMD run.py