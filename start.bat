@echo off
setlocal enabledelayedexpansion

REM Betik kendi dizininden calissin: aksi halde requirements.txt / hrma
REM bulunamiyordu ("Could not open requirements file" — 2026-07-15 geri donutu)
cd /d "%~dp0"

echo ==========================================
echo   HYBRID ROCKET MOTOR ANALYSIS TOOL
echo ==========================================
echo.

REM Check for Python installations (try different commands)
set PYTHON_CMD=
python --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_CMD=python
    goto :python_found
)

python3 --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_CMD=python3
    goto :python_found
)

py --version >nul 2>&1
if !errorlevel! equ 0 (
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

REM Python surum kapisi: 3.10-3.13 desteklenir. 3.14+ derlenmis bagimliliklar
REM (numpy<2, CoolProp, RocketCEA) icin wheel bulamayip kaynaktan derlemeye
REM calisiyor ve C derleyicisi olmadan patliyor (2026-07-15 numpy meson hatasi).
for /f "tokens=1,2 delims=." %%a in ('!PYTHON_CMD! -c "import sys;print(sys.version_info[0],sys.version_info[1])"') do (
    set PYMAJ=%%a
    set PYMIN=%%b
)
if !PYMAJ! neq 3 (
    echo Error: Python 3.10-3.13 required. Detected: !PYMAJ!.!PYMIN!
    pause
    exit /b 1
)
if !PYMIN! lss 10 (
    echo Error: Python 3.10 or newer required. Detected: 3.!PYMIN!
    pause
    exit /b 1
)
if !PYMIN! geq 14 (
    echo ==========================================================
    echo   Python 3.!PYMIN! is not supported for source install.
    echo ==========================================================
    echo Compiled dependencies numpy, CoolProp, RocketCEA do not ship
    echo 3.14+ wheels, so pip tries to build them from source and fails
    echo without a C compiler.
    echo.
    echo EASIEST FIX: download the ready-made installer instead of the
    echo source code: https://github.com/berketez/HRMA/releases/latest
    echo   Windows: HRMA-Setup-x.y.z.exe  ^(bundles Python 3.12 + everything^)
    echo.
    echo Or install Python 3.12 from https://www.python.org/downloads/
    pause
    exit /b 1
)

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

REM Install required packages.
REM --prefer-binary: pip mumkun oldugunca wheel kullansin, sdist derlemesin
REM (numpy meson build hatasinin ana sebebi kaynaktan derlemeye dusmesiydi).
!PYTHON_CMD! -m pip install --prefer-binary -r requirements.txt

if errorlevel 1 (
    echo.
    echo Error: Failed to install required packages!
    echo.
    echo Common solutions:
    echo 1. Check your internet connection
    echo 2. Run as Administrator if needed
    echo 3. Use Python 3.12 ^(3.14+ has no wheels for some packages^)
    echo 4. EASIEST: use the ready-made installer instead of source:
    echo    https://github.com/berketez/HRMA/releases/latest
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
if exist hrma\run_windows.py (
    echo Using Windows-optimized launcher...
    !PYTHON_CMD! hrma\run_windows.py
) else (
    echo Using standard launcher...
    !PYTHON_CMD! hrma\run.py
)

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo Application stopped with an error.
    pause
)