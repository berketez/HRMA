#!/bin/bash

# Rocket Motor Analysis - Cross-platform Startup Script

echo "=========================================="
echo "  ROCKET MOTOR ANALYSIS TOOL"
echo "=========================================="
echo

# Function to check for Python
# TEK KAYNAK — asagidaki gercek surum kapisi (PYMIN) ile AYNI sayilar.
# ÖH D22 · P10B3-07: eskiden bu fonksiyon 3.7 ariyor, hata metni "3.7+"
# diyordu, ama 46-56. satirlardaki gercek kapi 3.10 istiyordu. Kullanici
# 3.7 kurup geri geliyor ve ikinci kapida geri cevriliyordu.
PY_MIN_MAJOR=3
PY_MIN_MINOR=10
PY_MAX_MINOR=13

check_python() {
    # Adaylar sirayla denenir; SURUM KAPISINI GECEN ilki secilir. python3
    # bulundu diye kosulsuz kabul edilmez (eski davranis buydu ve hukmu
    # tamamen asagidaki ikinci kapiya birakiyordu).
    for cmd in python3 python; do
        if command -v "$cmd" &> /dev/null; then
            if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (${PY_MIN_MAJOR},${PY_MIN_MINOR}) else 1)" 2>/dev/null; then
                PYTHON_CMD="$cmd"
                return 0
            fi
        fi
    done
    return 1
}

# Check for Python installation
if ! check_python; then
    echo "Error: Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}-${PY_MIN_MAJOR}.${PY_MAX_MINOR} is required and was not found!"
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
if [ "$PYMAJ" -ne "$PY_MIN_MAJOR" ]; then
    echo "Error: Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}-${PY_MIN_MAJOR}.${PY_MAX_MINOR} required. Detected: $PYMAJ.$PYMIN"
    exit 1
fi
if [ "$PYMIN" -lt "$PY_MIN_MINOR" ]; then
    echo "Error: Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR} or newer required. Detected: ${PYMAJ}.$PYMIN"
    exit 1
fi
if [ "$PYMIN" -gt "$PY_MAX_MINOR" ]; then
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

# ---------------------------------------------------------------------------
# ÖH D18 / altyapi (P10B3-24) — bağımlılıklar KULLANICININ GENEL Python'una
# kurulmaz.
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (once_p10b3_14.json): bu betik requirements.txt'i doğrudan
# kullanıcının sistem Python'una kuruyordu; sanal ortam yoktu, --user yoktu
# ve HER AÇILIŞTA "pip install --upgrade pip" koşturuyordu. Üç sonucu vardı:
#   * HRMA'nın pinleri (numpy<2 gibi) kullanıcının başka projelerini bozuyor,
#     kullanıcının başka projeleri de HRMA'yı bozuyordu;
#   * yeni sistemlerde (PEP 668 "externally managed environment") kurulum
#     tamamen reddediliyor, kullanıcı çıkmaza giriyordu;
#   * her açılışta pip yükseltmesi ağ gerektiriyor ve çevrimdışı makinede
#     gereksiz gürültü/başarısızlık üretiyordu.
#
# Artık kurulum ve koşum PROJE İÇİ sanal ortamda (.venv) yapılır. pip
# yükseltmesi yalnız ortam İLK KURULDUĞUNDA bir kez koşar.
#
# FAIL-CLOSED: sanal ortam kurulamıyorsa sessizce genel Python'a DÖNÜLMEZ —
# yanlış yere kurmak, hiç kurmamaktan kötüdür. Neden ve çözüm adıyla söylenir.
VENV_DIR="$(cd "$(dirname "$0")" && pwd)/.venv"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating an isolated environment in .venv ..."
    if ! $PYTHON_CMD -m venv "$VENV_DIR"; then
        echo
        echo "Error: could not create the .venv virtual environment."
        echo
        echo "HRMA does not install its dependencies into your system Python:"
        echo "its pins (numpy<2 and the compiled wheels built against it)"
        echo "would collide with your other projects."
        echo
        echo "How to fix:"
        echo "1. Install the venv module, e.g. on Debian/Ubuntu:"
        echo "     sudo apt install python3-venv"
        echo "2. Or use the ready-made installer instead of the source tree:"
        echo "     https://github.com/berketez/HRMA/releases/latest"
        echo
        exit 1
    fi
    VENV_YENI=1
else
    VENV_YENI=0
fi

VENV_PY="$VENV_DIR/bin/python"

if [ "$VENV_YENI" = "1" ]; then
    # Yalnız ortam ilk kurulduğunda: eski pip bazı tekerlekleri çözemiyor.
    "$VENV_PY" -m pip install --upgrade pip
fi

# --prefer-binary: pip mümkün olduğunca tekerlek kullansın, kaynaktan
# derlemeye düşmesin (hrma/install.py ile aynı gerekçe).
if ! "$VENV_PY" -m pip install --prefer-binary -r requirements.txt; then
    echo
    echo "Error: Failed to install required packages!"
    echo
    echo "Common solutions:"
    echo "1. Check your internet connection"
    echo "2. Use Python 3.12 (3.14+ has no wheels for some packages)"
    echo "3. Delete the .venv directory and run this script again"
    echo "4. EASIEST: use the ready-made installer instead of source:"
    echo "     https://github.com/berketez/HRMA/releases/latest"
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

# Start the application — bağımlılıkların KURULDUĞU yorumlayıcıyla (.venv).
"$VENV_PY" hrma/run.py