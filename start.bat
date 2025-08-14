@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo   HYBRID ROCKET MOTOR ANALYSIS TOOL
echo ==========================================
echo.

REM Check for Python installations (try different commands)
set PYTHON_CMD=
python --version >nul 2>&1
if !errorlevel! eql 0 (
    set PYTHON_CMD=python
    goto :python_found
)

python3 --version >nul 2>&1
if !errorlevel! eql 0 (
    set PYTHON_CMD=python3
    goto :python_found
)

py --version >nul 2>&1
if !errorlevel! eql 0 (
    set PYTHON_CMD=py
    goto :python_found
)

echo Error: Python is not installed or not in PATH!
echo.
echo Please install Python from: https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:python_found
echo Found Python: !PYTHON_CMD!
!PYTHON_CMD! --version
echo.

echo Checking pip installation...
!PYTHON_CMD! -m pip --version >nul 2>&1
if errorlevel 1 (
    echo Error: pip is not available!
    echo Installing pip...
    !PYTHON_CMD! -m ensurepip --upgrade
)

echo Installing required packages...
echo This may take a few minutes on first run...
echo.

REM Upgrade pip first
!PYTHON_CMD! -m pip install --upgrade pip

REM Install required packages
!PYTHON_CMD! -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo Error: Failed to install required packages!
    echo.
    echo Common solutions:
    echo 1. Check your internet connection
    echo 2. Run as Administrator if needed
    echo 3. Try: pip install --user flask flask-cors numpy scipy plotly pandas waitress
    echo.
    pause
    exit /b 1
)

echo.
echo Installation completed successfully!
echo.
echo Starting web application...
echo The browser will open automatically at: http://localhost:5000
echo.
echo Press Ctrl+C in this window to stop the application
echo.

REM Start the application (try Windows-optimized version first)
if exist run_windows.py (
    echo Using Windows-optimized launcher...
    !PYTHON_CMD! run_windows.py
) else (
    echo Using standard launcher...
    !PYTHON_CMD! run.py
)

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo Application stopped with an error.
    pause
)